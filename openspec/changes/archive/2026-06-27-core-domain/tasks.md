# Tasks: `core-domain` — Persona Domain, Matching Policy, and Menores Privacy

**Status**: All 9 phases complete (2026-01-07). See `apply-progress.md` for full report.

- Phase 1 (Test infrastructure): ✅ Complete
- Phase 2 (Schema changes): ✅ Complete
- Phase 3 (Domain layer): ✅ Complete
- Phase 4 (Repository layer): ✅ Complete
- Phase 5 (Endpoint refactoring): ✅ Complete
- Phase 6 (Frontend simplification): ✅ Complete
- Phase 7 (Documentation): ✅ Complete
- Phase 8 (V0 cleanup): ✅ Complete
- Phase 9 (Verification): ✅ Complete — 22/22 tests pass, domain 100% coverage

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 700–800 |
| 400-line budget risk | Low |
| 800-line budget risk | Medium (tight margin; consider splitting) |
| Chained PRs recommended | No (single PR preferred) |
| Suggested split | single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

```text
Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low
```

> **NOTE**: The review budget is 800 lines per PR. The estimated 700–800 changed lines fit within one PR but with tight margin. An 800-line diff is large but reviewable. If the diff grows beyond 800, the user should decide whether to split the repository module into a separate PR. Delivery strategy `ask-on-risk` means we ask before apply.

---

## Task list

### Phase 1: Test infrastructure (foundation)

All subsequent tasks have tests. This phase ensures pytest works before any domain code is written.

---

### Task 1.1: Add dev dependencies for testing

**Phase**: 1
**Files**:

- `requirements.txt` (modify)

**What to do**:

1. Add `pytest`, `httpx`, `pytest-asyncio` to `requirements.txt`. The team already has `insightface`, `passlib`, `PyJWT` — verify these are present.
2. If the file has a `# dev` section, add there; otherwise add a comment-separated block.
3. Verify `pytest --version` shows a valid version.

**Depends on**: None

**Verifies**: Spec requirement "pytest infrastructure in place"

**Estimated lines**: +5

---

### Task 1.2: Create `tests/conftest.py` with base fixtures

**Phase**: 1
**Files**:

- `tests/conftest.py` (new)
- `tests/__init__.py` (new, empty)

**What to do**:

1. Create `tests/__init__.py` and `tests/domain/__init__.py` (empty).
2. Create `tests/conftest.py` with:
   - `sys.path` fix so `from app...` imports resolve when running `pytest` from repo root.
   - `client` fixture returning `fastapi.testclient.TestClient(app)`. Do NOT start the lifespan (no DB / DeepFace).
   - `policy` fixture returning `MatchingPolicy(threshold=0.55, conf_alta=0.40, conf_media=0.55)` (MatchingPolicy will be created in Task 3.2).
   - **Auth override**: Override `app.auth.get_current_admin` dependency in the `client` fixture so admin endpoint tests work without a DB. Return a dummy `Admin` dataclass instance.
   - `admin_token` fixture that returns a valid `Authorization: Bearer <token>` string (can be any string since the dependency is overridden).
   - `admin_headers` fixture returning `{"Authorization": admin_token}`.
3. Verify `pytest tests/` discovers the file.

**Depends on**: Task 1.1

**Verifies**: Spec requirement "pytest infrastructure in place", "Auth tests use Bearer token fixture"

**Estimated lines**: ~40

---

### Phase 2: Schema change

---

### Task 2.1: Add `es_menor` field to `AlertaFamiliar` schema

**Phase**: 2
**Files**:

- `app/schemas.py` (modify)

**What to do**:

1. Add `es_menor: bool = False` to the `AlertaFamiliar` Pydantic model, after `confianza` and before any `model_config`.
2. Add a docstring comment explaining: "Used by MenoresPrivacy to mask familiar_nombre for minors. Not surfaced to the user but included for uniform privacy handling."
3. Verify: `from app.schemas import AlertaFamiliar; a = AlertaFamiliar(person_id="x", image_url="x", coincidencia=50, confianza="media"); assert a.es_menor is False`

**Depends on**: None

**Verifies**: Spec requirement "AlertaFamiliar respects menores privacy", design decision for privacy.py

**Estimated lines**: +3

---

### Phase 3: Domain modules

These are the three core domain concepts. Each gets its own module and test file. Order: `matching` first (no dependencies), then `persona`, then `privacy` (depends on schemas).

---

### Task 3.1: Create `app/domain/__init__.py` barrel

**Phase**: 3
**Files**:

- `app/domain/__init__.py` (new)
- `app/domain/` (new directory)

**What to do**:

1. Create `app/domain/__init__.py` re-exporting `MatchingPolicy`, `Confianza`, `MenoresPrivacy`, `PersonaBase`, `Estado`, `Foto`.
2. Use lazy imports or `TYPE_CHECKING` to avoid circular dependencies.
3. Verify `from app.domain import MatchingPolicy, MenoresPrivacy` works after Tasks 3.2–3.4.

**Depends on**: None (directory setup)

**Verifies**: Module structure per design Section 1

**Estimated lines**: ~10

---

### Task 3.2: Create `app/domain/matching.py` + test file

**Phase**: 3
**Files**:

- `app/domain/matching.py` (new)
- `tests/domain/test_matching.py` (new)
- `app/domain/__init__.py` (update)

**What to do**:

1. Create `app/domain/matching.py` with:
   - `Confianza` type alias (`Literal["alta", "media", "baja"]`).
   - `MatchingPolicy` frozen dataclass: `threshold: float`, `conf_alta: float = 0.40`, `conf_media: float = 0.55`.
   - `is_match(self, distance: float) -> bool`: returns `True` iff `distance < self.threshold` (strict `<`).
   - `confidence_band(self, distance: float) -> Confianza`: `"alta"` if `< conf_alta`, `"media"` if `< conf_media`, else `"baja"`.
   - `match_percentage(self, distance: float) -> int`: delegates to `faces.distance_to_confidence(distance)` and truncates with `int()`. Add a code comment: "Sigmoid calibrated for InsightFace buffalo_l (k=12.0, midpoint=0.40). Replaces the old 1.2 divisor from Facenet512 era."
   - **NOTE**: `conf_media = 0.55` matches `Settings.match_threshold = 0.55` (InsightFace calibration). Do NOT use `0.50`.

2. Update `app/domain/__init__.py` to re-export `MatchingPolicy`, `Confianza`.

3. Create `tests/domain/test_matching.py` (≥14 tests):
   - `test_is_match_below_threshold` — `is_match(0.45)` → `True` (threshold=0.55)
   - `test_is_match_at_threshold` — `is_match(0.55)` → `False` (strict `<`)
   - `test_is_match_above_threshold` — `is_match(0.60)` → `False`
   - `test_is_match_zero_distance` — `is_match(0.0)` → `True`
   - `test_confidence_band_alta` — `confidence_band(0.30)` → `"alta"`
   - `test_confidence_band_media` — `confidence_band(0.45)` → `"media"`
   - `test_confidence_band_baja` — `confidence_band(0.60)` → `"baja"`
   - `test_confidence_band_at_alta_boundary` — `confidence_band(0.40)` → `"media"`
   - `test_confidence_band_at_media_boundary` — `confidence_band(0.55)` → `"baja"`
   - `test_match_percentage_sigmoid_typical` — `match_percentage(0.36)` → delegates to sigmoid; mock `faces.distance_to_confidence` or verify range (~60–65)
   - `test_match_percentage_zero` — `match_percentage(0.0)` → `100`
   - `test_match_percentage_at_threshold` — `match_percentage(0.55)` → ~16 (sigmoid value)
   - `test_match_percentage_large_distance` — `match_percentage(2.0)` → `0` (sigmoid asymptote)
   - `test_custom_threshold` — `MatchingPolicy(threshold=0.30).is_match(0.25)` → `True`

4. **Key testing note**: `match_percentage` delegates to `faces.distance_to_confidence` which imports insightface. To test without loading the model, either mock `faces.distance_to_confidence` in the test module or define `match_percentage` to accept an optional callable. Add a comment in matching.py explaining this testing concern.

5. Verify `pytest tests/domain/test_matching.py` passes.

**Depends on**: Task 1.2 (conftest), Task 3.1 (domain directory)

**Verifies**: Spec "Single source of truth for match threshold", "Percentage formula uses sigmoid", "MatchingPolicy has unit tests"

**Estimated lines**: ~45 (module) + ~80 (tests)

---

### Task 3.3: Create `app/domain/persona.py` + optional test file

**Phase**: 3
**Files**:

- `app/domain/persona.py` (new)
- `tests/domain/test_persona.py` (new, optional)
- `app/domain/__init__.py` (update)

**What to do**:

1. Create `app/domain/persona.py` with:
   - `Estado` enum: `BUSCADA = "buscada"`, `ENCONTRADA = "encontrada"`.
   - `Foto` frozen dataclass: `image_url: str`, `image_key: str`.
   - `PersonaBase` Pydantic model (internal domain model, NOT a response model):
     - Fields: `person_id: UUID`, `estado: Estado`, `es_menor: bool`, `nombre: str | None = None`, `apellido: str | None = None`, `edad: str | None = None`, `doc_tipo: str | None = None`, `doc_numero: str | None = None`, `telefono_contacto: str | None = None`, `refugio: str | None = None`, `telefono_responsable: str | None = None`, `doc_responsable: str | None = None`, `descripcion: str | None = None`, `ubicacion: str | None = None`, `codigo: str | None = None`, `photos: list[str] = []`, `distancia: float | None = None`, `moderacion: str = "aprobada"`.

2. Update `app/domain/__init__.py`.

3. (Optional) Create `tests/domain/test_persona.py` covering `Estado` enum values, `PersonaBase` validation, `photos` aggregation.

**Depends on**: Task 3.1

**Verifies**: Spec "Persona is a first-class entity"

**Estimated lines**: ~50 (module) + ~40 (tests, optional)

---

### Task 3.4: Create `app/domain/privacy.py` + test file

**Phase**: 3
**Files**:

- `app/domain/privacy.py` (new)
- `tests/domain/test_privacy.py` (new)
- `app/domain/__init__.py` (update)

**What to do**:

1. Create `app/domain/privacy.py` with:
   - `MenoresPrivacy` function (not a class) accepting `obj` of type `Candidato | PersonaAdmin | AlertaFamiliar` using `TypeVar`.
   - If `obj.es_menor is True`:
     - For `Candidato` and `PersonaAdmin`: return a new instance (`model_copy(update={...})`) with `nombre=None`, `apellido=None`.
     - For `AlertaFamiliar`: return with `familiar_nombre=None`.
   - If `obj.es_menor is False`: return the object unchanged (no copy needed, but must not mutate).
   - Use `isinstance` checks to handle the three types.
   - Docstring: "Applied at the API response boundary for ALL regular endpoints — public AND admin (Q1 revised). The original object is NOT mutated."
   - Import schema types from `app.schemas` (lazy import to avoid circular deps).

2. Update `app/domain/__init__.py` to re-export `MenoresPrivacy`.

3. Create `tests/domain/test_privacy.py` (≥8 tests):
   - `test_masks_candidato_minor` — `Candidato(es_menor=True, nombre="Juan", apellido="Pérez")` → `nombre=None`, `apellido=None`
   - `test_passes_candidato_adult` — `Candidato(es_menor=False, nombre="Rosa", ...)` → unchanged
   - `test_original_not_mutated_candidato` — original still has names after call
   - `test_masks_alerta_familiar_minor` — `AlertaFamiliar(es_menor=True, familiar_nombre="Ana")` → `familiar_nombre=None`
   - `test_passes_alerta_familiar_adult` — `AlertaFamiliar(es_menor=False, familiar_nombre="Carlos")` → preserved
   - `test_masks_persona_admin_minor` — `PersonaAdmin(es_menor=True, nombre="María")` → masked
   - `test_passes_persona_admin_adult` — `PersonaAdmin(es_menor=False, ...)` → preserved
   - `test_none_names_stay_none` — `Candidato(es_menor=True, nombre=None)` → no error

4. **BLOCKER**: AlertaFamiliar tests require Task 2.1 (es_menor field). Workaround: skip AlertaFamiliar tests or import lazily until Task 2.1 is done.

5. Verify `pytest tests/domain/test_privacy.py` passes.

**Depends on**: Task 1.2 (conftest), Task 3.1, Task 2.1 (AlertaFamiliar.es_menor)

**Verifies**: Spec "MenoresPrivacy is a single callable", "MenoresPrivacy has unit tests", "Menores privacy applied to ALL regular API responses"

**Estimated lines**: ~35 (module) + ~60 (tests)

---

### Phase 4: Repository module

All SQL moves here. The repository depends on MatchingPolicy from Phase 3.

---

### Task 4.1: Create `app/repositories/` barrel

**Phase**: 4
**Files**:

- `app/repositories/__init__.py` (new)
- `app/repositories/` (new directory)

**What to do**:

1. Create `app/repositories/__init__.py` with re-export of `PersonaRepository`.

**Depends on**: Task 3.1

**Estimated lines**: ~5

---

### Task 4.2: Create `app/repositories/persona.py` + test file

**Phase**: 4
**Files**:

- `app/repositories/persona.py` (new)
- `app/repositories/__init__.py` (update)
- `tests/repositories/test_persona_repo.py` (new, optional but recommended)

**What to do**:

1. Create `app/repositories/persona.py` with `PersonaRepository` class owning ALL SQL for `personas` and `persona_embeddings` tables:

   - `__init__(self, pool: ConnectionPool, policy: MatchingPolicy)`.
   - **Class SQL constants**:
     - `_INSERT_PERSONA` — INSERT one row into `personas` (18 columns: id, person_id, estado, es_menor, nombre, apellido, edad, doc_tipo, doc_numero, telefono_contacto, refugio, telefono_responsable, doc_responsable, descripcion, ubicacion, codigo, image_url, image_key). NO embedding column (it was dropped).
     - `_INSERT_EMBEDDING` — INSERT into `persona_embeddings` (foto_id, embedding, calidad_rostro).
     - `_SEARCH` — Public search with `ROW_NUMBER() OVER (PARTITION BY p.person_id ORDER BY pe.embedding <=> %s ASC)`, `WHERE p.moderacion = 'aprobada'`, optional `estado` filter. Gets best match per person.
     - `_SEARCH_ADMIN` — Same as `_SEARCH` but NO `moderacion` filter.
     - `_LIST_ADMIN` — Aggregation query: `SELECT person_id, max(estado), bool_or(es_menor), max(nombre), max(apellido), max(edad), max(doc_numero), max(refugio), max(ubicacion), coalesce(max(tel_resp), max(tel_contacto)), max(codigo), max(moderacion), array_agg(image_url), min(created_at) FROM personas {where} GROUP BY person_id ...`.
     - `_SET_MODERACION` — `UPDATE personas SET moderacion = %s WHERE person_id = %s`.
     - `_DELETE` — `DELETE FROM personas WHERE person_id = %s`.
     - `_SELECT_IMAGE_KEYS` — `SELECT image_key FROM personas WHERE person_id = %s`.

   - **Methods**:
     - `add(self, person_id, datos: dict, procesadas: list[tuple[bytes, str, list[tuple[Any, float]]]]) -> list[str]`:
       Insert one row per photo into `personas`, N embeddings per photo into `persona_embeddings`.
       Upload images via `storage.upload_image`. Returns list of URLs.
       Uses `pg_advisory_lock`? No — the team's DB schema uses `advisory_lock` only in `init_db()` to prevent concurrent schema creation. The `add` method uses a regular connection with `conn.execute` + `conn.commit()`.
       **IMPORTANT**: The `datos` dict keys must match the SQL placeholders (`estado`, `menor`, `nombre`, `apellido`, `edad`, `doc_tipo`, `doc_numero`, `tel_contacto`, `refugio`, `tel_resp`, `doc_resp`, `descripcion`, `ubicacion`, `codigo`).
       The dict values already have `menor` key (note: `es_menor` → `menor` in SQL param) — preserve this convention or normalize. See current `_insertar_fotos` call sites for the exact key names.

     - `search_by_estado(self, embedding, estado: str | None, limit: int) -> list[dict]`:
       Search with `moderacion='aprobada'` filter. Returns list of Candidato-shaped dicts with `distancia`, `coincidencia` (via `policy.match_percentage`), `confianza` (via `policy.confidence_band`).
       Does NOT apply privacy masking.

     - `search_admin(self, embedding, estado: str | None, limit: int) -> list[dict]`:
       Same as `search_by_estado` but NO moderacion filter.

     - `list_admin(self, limit: int, estado: str | None = None, moderacion: str | None = None) -> list[dict]`:
       List with optional estado and moderacion filters. Returns PersonaAdmin-shaped dicts.

     - `set_moderacion(self, person_id: str, valor: str) -> int`:
       Update `moderacion` for all rows with this `person_id`. Returns rowcount. **IMPORTANT**: Must commit inside the method.

     - `delete(self, person_id: str) -> int`:
       Fetch `image_key` values, delete from storage (best-effort, try/except per key), delete from DB. `ON DELETE CASCADE` handles `persona_embeddings`. Returns number of deleted photos.

   - **Row mapping methods**:
     - `_row_to_candidato_dict(self, row: tuple) -> dict`: Maps a search result row (from `_SEARCH` or `_SEARCH_ADMIN`) to a dict with keys matching `Candidato` fields (person_id, estado, es_menor, nombre, apellido, edad, refugio, ubicacion, telefono, descripcion, image_url, distancia, coincidencia, confianza). The `coincidencia` and `confianza` are computed via `self._policy`.
     - `_row_to_admin_dict(self, row: tuple) -> dict`: Maps an admin aggregation row (from `_LIST_ADMIN`) to a dict with keys matching `PersonaAdmin` fields.

2. Update `app/repositories/__init__.py`.

3. (Recommended) Create `tests/repositories/test_persona_repo.py` with in-memory fake:
   - Fake repository subclass that bypasses SQL and returns pre-canned row tuples.
   - Tests for `_row_to_candidato_dict` mapping (distance → coincidencia/confianza via policy).
   - Tests for `_row_to_admin_dict` mapping.
   - Test that privacy is NOT applied by the repository (no `MenoresPrivacy` call inside).
   - Use the `policy` fixture from conftest.

**Depends on**: Task 3.2 (MatchingPolicy), Task 3.3 (PersonaBase), Task 4.1 (repositories directory)

**Verifies**: Spec "PersonaRepository owns all SQL for personas and persona_embeddings", "Row-to-model mapping is centralized", "No raw SQL in app/main.py", "Multi-embeddings handled correctly", "Moderation filter applied"

**Estimated lines**: ~200 (module, heavy SQL) + ~70 (tests, optional)

---

### Phase 5: Endpoint refactor in `app/main.py`

This is the heart of the change. Remove all inline SQL, hardcoded thresholds, and scattered privacy logic. Wire the new domain and repository modules.

**IMPORTANT**: The existing endpoints reference `Depends(requiere_admin)` but `app/auth.py` only exports `get_current_admin`. During refactoring, fix the import and dependency name to use `get_current_admin`.

---

### Task 5.1: Wire `MatchingPolicy` and `PersonaRepository` at module scope

**Phase**: 5
**Files**:

- `app/main.py` (modify)

**What to do**:

1. **Add imports** at the top:
   - `from app.domain import MatchingPolicy, MenoresPrivacy`
   - `from app.repositories import PersonaRepository`
   - Keep existing imports from `app.auth` but replace `requiere_admin` with `get_current_admin` (fix the missing import bug).

2. **Remove** module-level constants: `CONF_ALTA`, `CONF_MEDIA`.
   **Remove** functions: `nivel_confianza`, `pct_coincidencia`, `_insertar_fotos`, `_buscar_mejor_por_persona`, `_buscar_por_estado`, `_fila_a_candidato`, `_COLS`, `_sel`.

3. After the import block and before `lifespan`, add module-level globals:
   - `_policy: MatchingPolicy | None = None`
   - `_repo: PersonaRepository | None = None`

4. Inside `lifespan`, after `get_pool()`, instantiate:
   - `_policy = MatchingPolicy(threshold=get_settings().match_threshold)`  (uses the config's `0.55`)
   - `_repo = PersonaRepository(pool=get_pool(), policy=_policy)`

5. Add helper accessors:
   - `def get_policy() -> MatchingPolicy: ...`
   - `def get_repo() -> PersonaRepository: ...`

6. Keep `gen_codigo()`, `_procesar_fotos()`, `_embedding_consulta()` as-is (they are not domain logic).

7. Verify `from app.main import get_policy, get_repo` works (import-time only).

**Depends on**: Task 3.2 (MatchingPolicy), Task 3.4 (MenoresPrivacy), Task 4.2 (PersonaRepository)

**Verifies**: Spec "Single source of truth for match threshold" (wire from config)

**Estimated lines**: net ~+15 (after removing ~30 lines of old constants and functions)

---

### Task 5.2: Refactor `POST /buscados` (familiar registration)

**Phase**: 5
**Files**:

- `app/main.py` (modify)

**What to do**:

1. Replace `_insertar_fotos(conn, person_id, datos, procesadas)` with `get_repo().add(person_id, datos, procesadas)`.
2. Replace `_buscar_por_estado(conn, embedding, "encontrada", limite)` with `get_repo().search_by_estado(embedding, estado="encontrada", limit=limite)`.
3. Replace `_fila_a_candidato(r)` iteration with: for each result dict `d`, construct `Candidato(**d)` then apply `MenoresPrivacy(Candidato(**d))`.
4. Remove manual `conn.commit()` and `with get_pool().connection() as conn:` — the repository handles transactions.
5. Keep validation logic (no photo, no embedding, missing name/doc checks).
6. Verify:
   - `pytest` passes.
   - Manual smoke test: `POST /buscados` with known photo returns candidates; minors have `nombre=None`.

**Depends on**: Task 5.1 (wire policy and repo), Task 4.2, Task 3.4

**Verifies**: Spec "Public search masks minor name", "Cross-flow alert and ranking share threshold"

**Estimated lines**: net -10

---

### Task 5.3: Refactor `POST /encontrados` — fix data preservation and AlertaFamiliar privacy

**Phase**: 5
**Files**:

- `app/main.py` (modify)

**This is the most critical task. It fixes two bugs: (1) data loss (names nulled before persist), (2) privacy leak (AlertaFamiliar exposes minor names).**

**What to do**:

1. **Fix data preservation**: Replace the current:

   ```python
   datos = dict(estado="encontrada", menor=es_menor,
                nombre=None if es_menor else nombre,
                apellido=None if es_menor else apellido, ...)
   ```

   With:

   ```python
   datos = dict(estado="encontrada", menor=es_menor,
                nombre=nombre, apellido=apellido, ...)
   ```

   Names are stored as-is regardless of `es_menor`. Privacy masking happens only at the response boundary.

2. Replace `_insertar_fotos` with `get_repo().add(...)`.
3. Replace `_buscar_por_estado(conn, embedding, "buscada", 1)` with `get_repo().search_by_estado(embedding, estado="buscada", limit=1)`.
4. Replace `if d < CONF_MEDIA` with `if get_policy().is_match(d)`.
5. Construct `AlertaFamiliar` using fields from the repo response dict, including `es_menor=best["es_menor"]`.
6. Apply `MenoresPrivacy(alerta)` to the alert object before returning.
7. Remove manual connection management.
8. **BLOCKER**: Task 2.1 must be done first (AlertaFamiliar needs `es_menor` field).

9. Verify:
   - `pytest` passes.
   - Manual smoke test: `POST /encontrados` with `es_menor=True` stores real names in DB, masks them in response.
   - Manual smoke test: Alert triggers when match found; `familiar_nombre=None` for matched minor.
   - Manual smoke test: `familiar_nombre` preserved for matched adult.

**Depends on**: Task 5.1, Task 4.2, Task 3.4, Task 2.1 (AlertaFamiliar.es_menor)

**Verifies**: Spec "Menores names stored, not nulled before persistence", "AlertaFamiliar respects menores privacy", "Data preservation fix"

**Estimated lines**: net -15

---

### Task 5.4: Refactor `POST /buscar` (admin search) — with MenoresPrivacy

**Phase**: 5
**Files**:

- `app/main.py` (modify)

**NOTE**: Per Q1 revised, MenoresPrivacy IS applied to admin endpoints (matches current `_fila_a_candidato` behavior, but now uniform).

**What to do**:

1. Replace inline SQL (`_buscar_mejor_por_persona`) with `get_repo().search_admin(embedding, estado=form_estado, limit=limite)`.
2. Construct `Candidato(**d)` from each result dict.
3. Apply `MenoresPrivacy(Candidato(**d))` to each candidate (this is the Q1 revised behavior — same as public endpoints).
4. Fix the auth dependency: change `Depends(requiere_admin)` to `Depends(get_current_admin)` and update the import.
5. Remove manual connection management.
6. Verify:
   - `pytest` passes.
   - Manual smoke test: `POST /buscar` with known photo → candidates; minors have `nombre=None`.

**Depends on**: Task 5.1, Task 4.2, Task 3.4

**Verifies**: Spec "Admin search masks minor name" (Q1 revised), "Menores privacy applied in regular admin endpoints"

**Estimated lines**: net -15

---

### Task 5.5: Refactor `GET /admin/personas` (admin list) — with MenoresPrivacy

**Phase**: 5
**Files**:

- `app/main.py` (modify)

**NOTE**: This is a new change. Currently `GET /admin/personas` returns `PersonaAdmin` with real names for minors (no masking). Per Q1 revised, it MUST mask minors.

**What to do**:

1. Replace inline SQL + manual `PersonaAdmin` construction with `get_repo().list_admin(limit=limite, estado=form_estado, moderacion=form_moderacion)`.
2. Construct `PersonaAdmin(**d)` from each result dict.
3. Apply `MenoresPrivacy(PersonaAdmin(**d))` to each result (Q1 revised: admin list masks minors).
4. Fix the auth dependency: `Depends(requiere_admin)` → `Depends(get_current_admin)`.
5. Remove manual connection management.
6. Verify:
   - `pytest` passes.
   - Manual smoke test: `GET /admin/personas` returns records; minors have `nombre=None`.

**Depends on**: Task 5.1, Task 4.2, Task 3.4

**Verifies**: Spec "Admin list masks minor name" (Q1 revised)

**Estimated lines**: net -15

---

### Task 5.6: Refactor `PATCH /admin/personas/{id}/moderacion` to use repository

**Phase**: 5
**Files**:

- `app/main.py` (modify)

**What to do**:

1. Replace inline `UPDATE personas SET moderacion = %s WHERE person_id = %s` with `get_repo().set_moderacion(person_id, valor)`.
2. Keep validation (`valor in ("aprobada", "rechazada", "pendiente")`, 404 if no rows updated).
3. Fix auth dependency: `Depends(requiere_admin)` → `Depends(get_current_admin)`.
4. Verify:
   - Manual smoke test: `PATCH /admin/personas/{id}/moderacion?valor=aprobada` works.

**Depends on**: Task 5.1, Task 4.2

**Verifies**: Spec "PATCH /admin/personas/{id}/moderacion updates status"

**Estimated lines**: net -5

---

### Task 5.7: Refactor `DELETE /admin/personas/{id}` to use repository

**Phase**: 5
**Files**:

- `app/main.py` (modify)

**What to do**:

1. Replace inline:

   ```python
   rows = conn.execute("SELECT image_key FROM personas WHERE person_id = %s", ...).fetchall()
   for (key,) in rows: storage.delete_image(key)
   conn.execute("DELETE FROM personas WHERE person_id = %s", ...)
   ```

   With `get_repo().delete(person_id)` (which handles storage cleanup internally).
2. Keep 404 check: if `delete` returns 0, raise HTTP 404.
3. Fix auth dependency: `Depends(requiere_admin)` → `Depends(get_current_admin)`.
4. Verify:
   - Manual smoke test: `DELETE /admin/personas/{id}` deletes and cleans up images.

**Depends on**: Task 5.1, Task 4.2

**Verifies**: Spec cleanup requirement for delete endpoint

**Estimated lines**: net -10

---

### Task 5.8: Endpoint + auth tests

**Phase**: 5
**Files**:

- `tests/test_auth.py` (new)
- `tests/conftest.py` (update if needed)

**What to do**:

1. Create `tests/test_auth.py` with these tests:
   - `test_admin_endpoint_requires_auth_buscar` — `POST /buscar` without token returns 401 (since the dependency override is removed for this test, or test with an invalid token).
   - `test_admin_endpoint_requires_auth_listar` — `GET /admin/personas` without token returns 401.
   - `test_admin_endpoint_requires_auth_moderar` — `PATCH /admin/personas/{id}/moderacion` without token returns 401.
   - `test_admin_endpoint_requires_auth_eliminar` — `DELETE /admin/personas/{id}` without token returns 401.
   - `test_admin_endpoint_with_valid_token` — `GET /admin/personas` with valid token headers returns 200 (dependency override provides a fake admin).

2. These tests use the `client` fixture which overrides `get_current_admin`. For the "without token" tests, remove the override or test against a sub-app without the override.

   **Strategy**: Create two client fixtures — one with auth override (default), one without. Or test by not sending the `Authorization` header while the override returns a fake admin anyway (which means the endpoint won't 401). Better approach: test that `get_current_admin` raises 401 when no token is provided, which is already covered by the auth module's own tests. For endpoint-level auth, use `app.dependency_overrides` to simulate token validation failure.

3. Add endpoint-level smoke tests that exercise the new repo methods through `TestClient`:
   - `test_registrar_busqueda_returns_candidates` — mock the repo to return canned results.
   - `test_registrar_encontrado_data_preservation` — verify names are NOT nulled in the datos dict.

**Depends on**: Task 1.2 (conftest with auth fixture), Task 5.2–5.7 (endpoint refactors)

**Verifies**: Spec "Admin endpoints require Bearer token", "Auth tests use Bearer token fixture"

**Estimated lines**: ~60

---

### Phase 6: Frontend simplification

---

### Task 6.1: Remove `es_menor` nulling from `frontend/index.html`

**Phase**: 6
**Files**:

- `frontend/index.html` (modify)

**What to do**:

The backend now applies `MenoresPrivacy` to ALL regular endpoints (public AND admin). The frontend must trust the backend.

1. **In `candHTML` function** (line ~137): Replace:

   ```javascript
   const titulo=c.es_menor?'<i>Menor protegido</i>':((c.nombre||'')+' '+(c.apellido||'')).trim()||'<i>sin nombre</i>';
   ```

   With:

   ```javascript
   const titulo=((c.nombre||'')+' '+(c.apellido||'')).trim()||'<i>sin nombre</i>';
   ```

   For minors, `c.nombre` is `null` from the backend, so `(c.nombre||'')` yields `''`, and the fallback `<i>sin nombre</i>` displays. This removes the `es_menor` check.

2. **In admin search render** (line ~194): Replace:

   ```javascript
   <div>${c.es_menor?'<i>Menor</i>':((c.nombre||'')+' '+(c.apellido||'')).trim()||'<i>sin nombre</i>'}</div>
   ```

   With:

   ```javascript
   <div>${((c.nombre||'')+' '+(c.apellido||'')).trim()||'<i>sin nombre</i>'}</div>
   ```

3. **In moderación render** (line ~175 inside `cargarModeracion`): Replace:

   ```javascript
   const t=p.es_menor?'<i>Menor protegido</i>':((p.nombre||'')+' '+(p.apellido||'')).trim()||'<i>sin nombre</i>';
   ```

   With:

   ```javascript
   const t=((p.nombre||'')+' '+(p.apellido||'')).trim()||'<i>sin nombre</i>';
   ```

4. Verify manually: Public search shows "sin nombre" for minors (backend returns `nombre=None`). The frontend no longer needs its own privacy logic.

**Depends on**: Task 5.2 (backend privacy applied to public endpoints), Task 5.4 and 5.5 (backend privacy applied to admin endpoints)

**Verifies**: Spec "Frontend no longer applies its own nulling logic"

**Estimated lines**: net -3 (3 lines changed)

---

### Task 6.2: (Optional) Automated check for response shape

**Phase**: 6
**Files**:

- `tests/test_frontend_compat.py` (new, optional)

**What to do**:

1. Create a test that calls the public endpoints through `TestClient` and verifies that `nombre=None` for minors in the response JSON.
2. This is a bonus test that validates the backend contract the frontend depends on.

**Depends on**: Task 6.1

**Verifies**: End-to-end contract verification

**Estimated lines**: ~30 (optional)

---

### Phase 7: Documentation

---

### Task 7.1: Rewrite `CLAUDE.md`

**Phase**: 7
**Files**:

- `CLAUDE.md` (rewrite)

**What to do**:

Rewrite to describe the current production stack:

- **What it is**: FastAPI service for facial-recognition‑based person reunification. Uses InsightFace buffalo_l (ArcFace w600k_r50, 512-dim) with RetinaFace detector for embeddings and pgvector (Postgres+HNSW) for vector search. Images stored on DigitalOcean Spaces (fallback to local disk).
- **How to run**: `docker-compose up` or `uvicorn app.main:app`.
- **Architecture**: Domain model (`app/domain/`), repository (`app/repositories/`), FastAPI endpoints (`app/main.py`), schema (`app/schemas.py`), face engine (`app/faces.py`), cloud storage (`app/storage.py`), auth (`app/auth.py`).
- **Key config**: `match_threshold=0.55` in `.env`, model `buffalo_l`, detector `RetinaFace`.
- **Auth**: JWT-based admin authentication. `POST /admin/login` returns token. All admin endpoints require `Authorization: Bearer <token>`.
- **Moderation**: `moderacion='aprobada'` filter on public searches. Admin can approve/reject.
- **Privacy**: Minor names stored in DB but masked in all regular API responses via `MenoresPrivacy`.
- **Testing**: `pytest` from repo root. Tests in `tests/`.
- **Remove ALL references** to: ChromaDB, `LoadImage`, `SearchImage`, root `main.py`, `database/` directory, Facenet512, `1.2` divisor, `haarcascade_frontalface_default.xml`.

**Depends on**: All Phase 1–6 tasks

**Verifies**: Spec "Documentation reflects current production stack"

**Estimated lines**: ~80 (rewrite)

---

### Task 7.2: Rewrite `AGENTS.md`

**Phase**: 7
**Files**:

- `AGENTS.md` (rewrite)

**What to do**: Same as Task 7.1.

**Depends on**: Task 7.1

**Estimated lines**: ~80 (rewrite)

---

### Phase 8: Cleanup

---

### Task 8.1: Delete v0 prototype files

**Phase**: 8
**Files to delete**:

- `load_image.py` (repo root)
- `search_image.py` (repo root)
- `main.py` (repo root — NOT `app/main.py`)
- `haarcascade_frontalface_default.xml` (repo root)

**What to do**:

1. Delete each file.
2. Update `.dockerignore` and `.gitignore` if they reference deleted files (check for `load_image.py`, `search_image.py`, `haarcascade*` entries — they may need cleanup but are harmless if stale).
3. Verify: `grep -rn "load_image\|search_image" app/` returns no imports from the deleted files.

**Depends on**: Verification that no remaining code imports these files

**Verifies**: Spec "v0 prototype files removed"

**Estimated lines**: net -4 files

---

### Task 8.2: Verify `.gitignore` and `.dockerignore` consistency

**Phase**: 8
**Files**:

- `.gitignore` (check)
- `.dockerignore` (check)

**What to do**:

1. Ensure `database/` (ChromaDB persistence) and `env.py` are still in `.gitignore`.
2. Ensure deleted v0 files are no longer referenced (or update to reflect they're gone).
3. No other changes needed.

**Depends on**: Task 8.1

**Estimated lines**: 0 (verification only)

---

### Phase 9: Verification

---

### Task 9.1: Run full test suite

**Phase**: 9
**Files**: None (verification only)

**What to do**:

1. Run `pytest` from repo root — all tests pass green.
2. Run `pytest --cov=app/domain --cov=app/repositories --cov-report=term-missing` and verify ≥80% line coverage on new modules (`app/domain/`, `app/repositories/`).
3. Check for remaining raw SQL in `app/main.py`: `grep -n "SELECT\|INSERT\|UPDATE\|DELETE" app/main.py` should show NO SQL for `personas` or `persona_embeddings` tables.

**Depends on**: All Tasks 1–8

**Verifies**: All spec requirements

**Estimated lines**: 0 (verification only)

---

### Task 9.2: Manual smoke tests

**Phase**: 9
**Files**: None (verification only)

**What to do** (requires running service with DB):

```bash
# 1. Health check
curl -s http://localhost:8000/health | jq

# 2. Public search: minors have nombre=None
curl -X POST http://localhost:8000/buscados \
  -F "files=@known_minor_photo.jpg" \
  -F "nombre=Test" -F "apellido=User" | jq '.coincidencias[] | {nombre, apellido, es_menor}'

# 3. Admin search (Q1 revised): minors STILL have nombre=None
# Get token first
TOKEN=$(curl -s -X POST http://localhost:8000/admin/login \
  -H "Content-Type: application/json" \
  -d '{"usuario":"admin","password":"reencuentros2026"}' | jq -r '.token')
curl -X POST http://localhost:8000/buscar \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@known_minor_photo.jpg" -F "limite=5" | jq '.[] | {nombre, apellido, es_menor}'

# 4. Admin list (Q1 revised): minors have nombre=None
curl -s http://localhost:8000/admin/personas \
  -H "Authorization: Bearer $TOKEN" | jq '.[] | select(.es_menor==true) | {nombre, apellido}'

# 5. POST /encontrados: names stored in DB, masked in response
curl -X POST http://localhost:8000/encontrados \
  -F "files=@minor_photo.jpg" \
  -F "es_menor=true" \
  -F "refugio=Test" \
  -F "telefono_responsable=123" \
  -F "doc_responsable=ABC" | jq '{codigo, alerta: .alerta | {familiar_nombre, confianza}}'

# 6. AlertaFamiliar: for minor match, familiar_nombre is None
# (requires a matching buscada record; check via the /encontrados endpoint)

# 7. Moderacion: approve a pending record
curl -X PATCH "http://localhost:8000/admin/personas/{id}/moderacion?valor=aprobada" \
  -H "Authorization: Bearer $TOKEN"

# 8. Delete: remove a record
curl -X DELETE "http://localhost:8000/admin/personas/{id}" \
  -H "Authorization: Bearer $TOKEN"

# 9. Unauthenticated admin endpoint returns 401
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/admin/personas
# Expected: 401
```

**Depends on**: All Tasks 1–8

**Verifies**: End-to-end validation of all spec requirements

**Estimated lines**: 0 (verification only)

---

## Verification Matrix

| Spec requirement | Verified by tasks |
|---|---|
| Single source of truth for match threshold | Task 3.2 (MatchingPolicy), Task 5.1 (wire from config) |
| Percentage formula uses sigmoid from faces.distance_to_confidence | Task 3.2 (match_percentage delegates), Task 9.1 (coverage) |
| Cross-flow alert and ranking list share the same threshold | Task 5.2 (public search), Task 5.3 (alert via is_match) |
| Benchmark thresholds isolated from production | Task 3.2 (no import from evaluate.py) |
| Persona is a first-class entity | Task 3.3 (persona.py with Estado, Foto, PersonaBase) |
| PersonaRepository owns all SQL for personas and persona_embeddings | Task 4.2 (repository module), Task 9.1 (grep check) |
| Row-to-model mapping is centralized | Task 4.2 (_row_to_candidato_dict, _row_to_admin_dict) |
| No raw SQL in app/main.py | Task 5.1–5.7 (refactor), Task 9.1 (grep check) |
| Multi-embeddings per photo (base + rotation augmentations) | Task 4.2 (add takes procesadas with N embeddings per photo, ROW_NUMBER search) |
| Menores names stored, not nulled before persistence | Task 5.3 (fix data preservation in POST /encontrados) |
| MenoresPrivacy is a single callable | Task 3.4 (privacy.py handles Candidato, PersonaAdmin, AlertaFamiliar) |
| Menores privacy applied to ALL regular API responses (public AND admin) | Task 5.2 (public), Task 5.3 (AlertaFamiliar), Task 5.4 (admin search), Task 5.5 (admin list) |
| AlertaFamiliar respects menores privacy (bug fix) | Task 2.1 (es_menor field), Task 5.3 (MenoresPrivacy applied to alert) |
| AlertaFamiliar preserves non-minor name | Task 5.3 (MenoresPrivacy passthrough for adults) |
| Frontend no longer applies own nulling logic | Task 6.1 (index.html), Task 6.2 (optional contract test) |
| Admin endpoints require Bearer token | Task 5.8 (auth tests), auth dependency preserved in all admin endpoints |
| Bearer token validated against DB via JWT | Task 5.1 (fix `requiere_admin` → `get_current_admin`), auth integration |
| PATCH /admin/personas/{id}/moderacion updates status | Task 5.6 (refactor to repo), Task 9.2 (smoke test) |
| DELETE /admin/personas/{id} removes person + photos | Task 5.7 (refactor to repo with storage cleanup), Task 9.2 (smoke test) |
| Public searches filter by moderacion='aprobada' | Task 4.2 (_SEARCH constant), Task 5.2 (public search uses search_by_estado) |
| Admin can list by moderacion status | Task 4.2 (list_admin with moderacion filter), Task 5.5 (endpoint passes filter) |
| v0 prototype files removed | Task 8.1 (delete files), Task 9.1 (verify deletion) |
| Documentation reflects current production stack | Task 7.1 (CLAUDE.md), Task 7.2 (AGENTS.md) |
| pytest infrastructure in place | Task 1.1 (dev deps), Task 1.2 (conftest.py) |
| MatchingPolicy has unit tests (≥14 tests) | Task 3.2 (test_matching.py) |
| MenoresPrivacy has unit tests (≥8 tests) | Task 3.4 (test_privacy.py) |
| Auth tests use Bearer token fixture | Task 1.2 (conftest admin_token/admin_headers), Task 5.8 (test_auth.py) |
| Test coverage ≥80% on app/domain/ and app/repositories/ | Task 9.1 (coverage check) |

---

## Deployment order

1. **Backend first** — Tasks 1–5 (domain, repository, endpoint refactors) can be deployed without frontend changes.
2. **Verify backend** — Run Task 9.2 smoke tests to confirm privacy is correctly applied.
3. **Frontend** — Deploy Task 6.1 after backend is verified.
4. **Docs + cleanup** — Tasks 7–8 last.

## Rollback notes

- Revert `app/main.py`, `app/schemas.py` to pre-change state.
- Remove `app/domain/` and `app/repositories/` directories.
- Delete `tests/` directory and dev dependencies from `requirements.txt`.
- Restore `frontend/index.html` if deployed.
- Revert `CLAUDE.md` / `AGENTS.md` if updated.
- **Do NOT** restore deleted v0 files — they are listed in `.dockerignore` and safe to remove.
- **Data note**: After rollback, minor names stored by the new code persist in the DB (`nombre`/`apellido` no longer nulled before persist). If the product requirement is "never store," a data cleanup script (`UPDATE personas SET nombre=NULL, apellido=NULL WHERE es_menor=true`) would be needed.
