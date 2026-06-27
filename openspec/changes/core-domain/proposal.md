# Proposal: `core-domain` — Persona Domain, Matching Policy, and Menores Privacy

## Intent

The `core-domain` change consolidates three scattered concepts that today live as duplicated or inconsistent code across the FastAPI service: how we decide a face match is real, what a "person" means in our data model, and how we protect minors' identities. By giving each concept a single, testable home, we reduce the risk of privacy leaks, calibration drift, and contradictory thresholds—while making the codebase safe for future contributors who are not facial-recognition specialists.

Since this proposal was first written, the team merged major changes from `origin/felipe` (InsightFace buffalo_l, multi-embeddings, auth, moderation). This updated proposal reflects the new codebase and re-decides Q1 and Q4 in light of those changes.

## Decisions

The following product decisions were confirmed during the proposal question round:

1. **Minor names: store in DB; mask in ALL regular endpoints; special super-admin endpoint is future work** (`Q1` revised)
   - The database retains the minor's real name. `registrar_encontrado` must **not** null `nombre`/`apellido` before persistence.
   - `_fila_a_candidato` already masks `nombre`/`apellido` to `None` for all endpoints that use it (`/buscados`, `/encontrados`, `/buscar`, `/admin/personas`). This behavior is kept for this change.
   - `AlertaFamiliar` must apply the same privacy protocol: `familiar_nombre=None` when the matched person is a minor.
   - A future change (out of scope for this SDD) may add a "super-admin with role" endpoint that bypasses the mask for minor names.

2. **Cross-flow alert and ranking share the same threshold** (`Q2`)
   - `AlertaFamiliar` and the ranking list both use the single operational threshold. There is no separate `alert_threshold` or `display_threshold`.

3. **Threshold values live as Python constants in `MatchingPolicy`, loaded from `config.py`** (`Q3`)
   - The operational threshold is wired from `Settings.match_threshold`. Confidence bands (`CONF_ALTA`, `CONF_MEDIA`) are class/module constants. No YAML/JSON calibration file is introduced.

4. **Percentage display (`pct_coincidencia`) uses the team's sigmoid, not the old `1.2` divisor** (`Q4` obsolete → new behavior)
   - The `1.2` divisor question is obsolete. The team replaced `pct_coincidencia` with `faces.distance_to_confidence`, a sigmoid calibrated for InsightFace buffalo_l (`confidence_sigmoid_k=12.0`, `confidence_sigmoid_midpoint=0.40`).
   - `MatchingPolicy.match_percentage(distance)` delegates to this function.

5. **Face model: InsightFace buffalo_l** (`Q5` new)
   - The change adopts the team's choice of InsightFace buffalo_l (ArcFace w600k_r50, 512-dim, RetinaFace detector).
   - `Settings.face_model` and `Settings.face_detector` reflect this choice.
   - Old Facenet512 embeddings are **not** compatible with the new model. The DB migration (in `app/database.py`) drops the old `personas.embedding` column and creates `persona_embeddings`. Old data is lost; the team re-registers as needed.

6. **Multi-embeddings per photo** (`Q6` new)
   - Each registered photo generates N embeddings (1 base + 2 augmented embeddings from rotations ±15°), stored in `persona_embeddings`.
   - The repository's search uses `ROW_NUMBER() OVER (PARTITION BY p.person_id ORDER BY pe.embedding <=> %s ASC)` to get the best match per person.
   - This is reflected in the new `PersonaRepository.search_by_estado` and `search_admin` methods.

7. **Auth: admin endpoints require Bearer token** (`Q7` new)
   - `/admin/login` returns a token. The token = `sha256("reencuentros::" + admin_password)`.
   - `/buscar`, `/admin/personas`, `PATCH /admin/personas/{id}/moderacion`, and `DELETE /admin/personas/{id}` all use `Depends(requiere_admin)`.
   - Tests must include the Bearer token fixture.

8. **Moderation filter** (`Q8` new)
   - All public search queries filter by `moderacion = 'aprobada'`.
   - Admin can list by `moderacion=pendiente|rechazada|aprobada` for review.
   - `PATCH /admin/personas/{id}/moderacion` updates the value.

## Why now

Four problems are actively hurting the product today, and the team's recent merge added new surface area that makes consolidation urgent:

1. **Live privacy bug**: When a rescuer registers a found child, the cross-flow alert (`AlertaFamiliar`) exposes the child's real name because the menores privacy rule is not applied there. This is a live data-protection failure.
2. **Privacy protocol still duplicated**: `registrar_encontrado` nulls minor names before database insertion (lines 263–264), `_fila_a_candidato` masks for all paths including admin (line 222), and `AlertaFamiliar` does NOT apply the protocol (lines 277–281). The leak is still live, and data is still being discarded before persist.
3. **Calibration drift**: `config.py` defines `match_threshold = 0.55`, but `main.py` ignores it and uses hardcoded `CONF_ALTA = 0.40` and `CONF_MEDIA = 0.55`. The documented calibration does not consistently drive the actual behavior.
4. **Threshold inconsistency**: The cross-flow alert uses `d < CONF_MEDIA` which happens to equal `match_threshold` numerically (0.55) but conceptually should be the same `MatchingPolicy.is_match()` call. The admin `/buscar` endpoint returns every row with no cutoff; and the benchmark script (`evaluate.py`) uses its own threshold dictionary.
5. **Multi-embedding SQL is inline and complex**: The team's new `persona_embeddings` table and `ROW_NUMBER() OVER ...` query live entirely in `app/main.py`. This SQL should be owned by a repository, not scattered across endpoint handlers.
6. **Zero tests**: There is no pytest infrastructure. Any refactor of matching logic, privacy rules, or the new auth/moderation flows is unguarded, which means we cannot safely fix the privacy bug without also risking regressions in the matching flow.

## Scope

### In scope

- **MatchingPolicy module**: One source of truth for match threshold, confidence bands (`alta` / `media` / `baja`), and percentage conversion (now delegating to the sigmoid in `faces.distance_to_confidence`).
- **Persona domain object + repository**: A single Python entity that represents "one person with N photos," plus a repository that owns all SQL for the `personas` and `persona_embeddings` tables. Replaces scattered SQL strings, raw `dict` mappings, and duplicated row-to-model conversion. Handles the moderation filter (`moderacion = 'aprobada'`) for public searches.
- **Menores privacy protocol**: A single serializer/policy that nulls `nombre`/`apellido` for minors **at the API response boundary**, fixing the `AlertaFamiliar` leak, stopping the pre-persist nulling in `registrar_encontrado`, and removing duplicated nulling logic in the frontend.
- **Data-preservation fix**: Stop nulling minor names before database insertion so the original data is retained; masking happens only on output, for all regular endpoints.
- **Admin auth wiring**: Ensure the new `PersonaRepository` and `MatchingPolicy` are available inside authenticated admin endpoints; tests must include the Bearer token fixture.
- **Dead-code cleanup**: Delete the v0 ChromaDB prototype files (`load_image.py`, `search_image.py`, root `main.py`, `haarcascade_frontalface_default.xml`).
- **Documentation update**: Rewrite `CLAUDE.md` / `AGENTS.md` to describe the current pgvector / InsightFace buffalo_l / FastAPI production stack.
- **pytest infrastructure**: Add pytest, `httpx`, and `pytest-asyncio` as dev dependencies; create at least a minimal `conftest.py` and starter tests for the new domain modules.

### Out of scope (defer to later changes)

- Re-introducing the old `1.2` divisor for percentage display (the sigmoid replaces it).
- The special "super-admin with role" endpoint that bypasses the menores mask (deferred to a future change).
- Changing the face model or detector (InsightFace buffalo_l + RetinaFace stays; the team already made this change).
- Changing the moderation workflow logic (the team already has `PATCH /admin/personas/{id}/moderacion` and the `moderacion` column).
- Changing the vector DB or index (pgvector HNSW stays).
- Adding migrations beyond the existing `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` and the team's `DROP COLUMN IF EXISTS` patterns.
- Full enum/CHECK constraint on `estado` in the database schema (will be enforced in Python/Pydantic only in this change; a DB-level constraint may come later after a data audit).
- Rewriting `ARQUITECTURA.md` (that doc drift is tracked separately; `sdd-sync` will handle it).
- Frontend framework migration (the single-file HTML stays; only the duplicated privacy nulling is removed).
- The team's deployment docs (`DOCKER.md`, `DEPLOY.md`, `API.md`, `.github/workflows/deploy.yml`, `Dockerfile.standalone`, `docker/standalone/*`) — these are new and correct; no changes needed.

## Product outcomes

After this change lands, the following should be true:

- **The menores privacy rule is enforced in one place**: No minor name appears in public API responses (`/buscados`, `/encontrados`, `AlertaFamiliar`). Regular admin endpoints (`/buscar`, `/admin/personas`) also mask minor names because they share `_fila_a_candidato`. The frontend no longer needs its own nulling logic.
- **Minor names are preserved in the database**: Registering a found minor stores the submitted name; it is masked only when serialized for wire responses. `registrar_encontrado` no longer nulls before insert.
- **AlertaFamiliar no longer leaks minor names**: The cross-flow alert applies the same privacy protocol as the ranking list.
- **All threshold values come from one module**: `config.py`'s `match_threshold` is wired into the application through `MatchingPolicy`. There are no hidden constants in endpoint files.
- **Confidence bands and match percentage are consistent**: The same policy decides whether a row is a match, what band it falls into, and what percentage to show. The percentage display uses the sigmoid (`faces.distance_to_confidence`) calibrated for InsightFace buffalo_l.
- **The cross-flow alert and the ranking list use the same threshold**: There is no separate alert threshold; both flows consult the single `MatchingPolicy.is_match()`.
- **Multi-embeddings are handled correctly**: `PersonaRepository` encapsulates the `ROW_NUMBER() OVER (PARTITION BY ...)` logic for `persona_embeddings`. No raw SQL for embeddings remains in `app/main.py`.
- **Moderation filter is applied everywhere**: Public searches always filter by `moderacion = 'aprobada'`. Admin searches can optionally filter by moderation status.
- **Admin auth is consistent**: All admin endpoints (`/buscar`, `/admin/personas`, moderation, delete) require the Bearer token.
- **The codebase has starter tests**: `pytest` passes in CI, and the new `MatchingPolicy` and `MenoresPrivacy` modules have ≥80% line coverage.

## Affected areas

| File | Nature of change |
|------|-----------------|
| `app/main.py` | Heavy refactor: remove `_insertar_fotos`, `_buscar_mejor_por_persona`, `_buscar_por_estado`, `_fila_a_candidato`, `nivel_confianza`, `pct_coincidencia`, `CONF_ALTA`, `CONF_MEDIA`; delegate to repository and policy modules. Fix `registrar_encontrado` to NOT null names before persist. Fix `AlertaFamiliar` construction to apply privacy protocol. Wire `MatchingPolicy` and `PersonaRepository` at module scope. |
| `app/config.py` | Ensure `match_threshold` is consumed by the new `MatchingPolicy`; no breaking changes to settings schema. Minor: `face_model` / `face_detector` fields may be added for documentation. |
| `app/schemas.py` | Add `es_menor: bool = False` to `AlertaFamiliar` so `MenoresPrivacy` can handle it uniformly. Keep existing `LoginBody` / `LoginResp` models. |
| `app/database.py` | **Unchanged** — the team's schema (`persona_embeddings`, `moderacion`, `pg_advisory_lock`) is correct. |
| `app/faces.py` | **Unchanged** — the team's InsightFace buffalo_l implementation is correct. |
| `app/storage.py` | **Unchanged** — local fallback is correct. |
| **New** `app/domain/matching.py` | New `MatchingPolicy` class with `is_match`, `confidence_band`, `match_percentage` (delegates to `faces.distance_to_confidence`). |
| **New** `app/domain/privacy.py` | New `MenoresPrivacy` callable: takes a `Candidato`, `PersonaAdmin`, or `AlertaFamiliar` and returns a copy with masked names when `es_menor=True`. |
| **New** `app/domain/persona.py` | New `Persona` entity (dataclass or Pydantic model), `Estado` enum, `Foto` dataclass. |
| **New** `app/repositories/persona.py` | New `PersonaRepository` owning all SQL for `personas` and `persona_embeddings`. Handles `ROW_NUMBER()` search, moderation filters, admin aggregation, and row-to-model mapping. |
| `frontend/index.html` | Remove duplicated `es_menor` nulling in `candHTML` and admin search render; trust backend. |
| `CLAUDE.md`, `AGENTS.md` | Rewrite to describe current production stack (pgvector, InsightFace buffalo_l, FastAPI). |
| `requirements.txt` | Add `pytest`, `httpx`, `pytest-asyncio` to dev section (or new `requirements-dev.txt`). |
| **New** `tests/conftest.py` | Minimal pytest + FastAPI test client setup. Add Bearer token fixture for admin endpoints. |
| **New** `tests/domain/test_matching.py` | Unit tests for `MatchingPolicy`. |
| **New** `tests/domain/test_privacy.py` | Unit tests for `MenoresPrivacy`. |

## Cleanup

### Files to delete

| File | Reason |
|------|--------|
| `load_image.py` | v0 ChromaDB prototype; uses wrong model (Facenet, not InsightFace). |
| `search_image.py` | v0 ChromaDB prototype; hardcoded `< 1` cosine threshold. |
| `main.py` (repo root, NOT `app/main.py`) | v0 scratchpad that imports the two classes above. |
| `haarcascade_frontalface_default.xml` | Never referenced by current code; DeepFace/InsightFace manage their own detection. |

### Docs to update

| File | Update |
|------|--------|
| `CLAUDE.md` | Replace ChromaDB/Facenet v0 description with pgvector/InsightFace buffalo_l/FastAPI production stack. |
| `AGENTS.md` | Same as `CLAUDE.md` (it is an alias/copy). |

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Live privacy bug persists** if `AlertaFamiliar` is missed during refactor | Medium | Critical | Add an explicit test: "`AlertaFamiliar` response for `es_menor=True` has `familiar_nombre=None`". |
| **Old data is lost** (Facenet512 embeddings cannot be migrated to InsightFace) | High (already happened) | Medium | The team already accepted re-registration. The migration drops the old `embedding` column. Document that re-registration is required. |
| **Auth is bearer-only** (no per-user tracking) | N/A (current state) | Low | For a humanitarian app with a single admin, this is acceptable. Can be hardened later (e.g., JWT with expiry). |
| **Calibration drift** if threshold is moved without validating against real data | Low | High | Keep the numeric value `0.55` unchanged in this change; only consolidate its location. Do not recalibrate. |
| **Migration risk** if `estado` gets a DB CHECK constraint on existing data | Low | Medium | Defer DB-level constraint to a later change with a data audit. Enforce `estado` in Python/Pydantic only. |
| **Zero tests guarding the refactor** | High | High | Add pytest infra as part of this change; write unit tests for `MatchingPolicy` and `MenoresPrivacy` before touching `app/main.py`. |
| **Wire-format change** — `AlertaFamiliar` will now apply privacy | Medium | Medium | This is a bug fix. Document in release notes that `familiar_nombre` may now be `None` for minors. |
| **Data model shift** — storing minor names in DB instead of NULL | Medium | Medium | The DB will now contain minor names. Access control shifts from "data not stored" to "data stored but masked on public output." Operational discipline (who has admin access) becomes the control. |
| **Frontend regression** if removed nulling logic depends on backend that fails | Low | Medium | The backend serializer must be applied to every public endpoint before the frontend change is safe. Implement backend first, then frontend. |

## Rollback

If the change ships and breaks production:

1. **Revert the Python code**: Roll back `app/main.py`, `app/config.py`, `app/schemas.py` to the pre-change state. Remove the new `app/domain/` and `app/repositories/` directories.
2. **Revert the frontend**: Restore `frontend/index.html` to its pre-change state (with client-side nulling).
3. **Database**: No schema migration is required for rollback. However, because the new code stores minor names in the DB (instead of NULL), reverting the code does **not** remove those names. If the product intent is "never store," a data cleanup script would be needed after rollback.
4. **Tests**: Remove `tests/` directory and dev dependencies from `requirements.txt` (or keep them—they are harmless).
5. **Docs**: Revert `CLAUDE.md` / `AGENTS.md` if they were updated.
6. **Dead code**: Do NOT restore the deleted v0 files; they are already listed in `.dockerignore` and their absence is safe.

## Success criteria

1. **Privacy (all regular endpoints)**: No minor name appears in any regular API response (`/buscados`, `/encontrados`, `/buscar`, `/admin/personas`, `AlertaFamiliar`). All regular endpoints return `nombre=None` and `apellido=None` (or `familiar_nombre=None`) for `es_menor=True`.
2. **Privacy (data preservation)**: `registrar_encontrado` stores real `nombre` and `apellido` in the database even when `es_menor=True`.
3. **Threshold consolidation**: All threshold values come from one module (`MatchingPolicy`). `config.py`'s `match_threshold=0.55` is wired into application logic.
4. **Shared threshold**: The cross-flow alert and the ranking list share the same threshold; no separate `alert_threshold` is exposed.
5. **Sigmoid percentage**: `MatchingPolicy.match_percentage` delegates to `faces.distance_to_confidence`. The old `1.2` divisor is gone.
6. **Domain clarity**: `PersonaRepository` owns all SQL for the `personas` and `persona_embeddings` tables. No raw SQL strings remain in `app/main.py`.
7. **Multi-embeddings**: `PersonaRepository.search_by_estado` correctly handles the `persona_embeddings` table with `ROW_NUMBER() OVER (PARTITION BY ...)`.
8. **Moderation filter**: Public searches always include `moderacion = 'aprobada'` in their WHERE clause.
9. **Admin auth**: All admin endpoints (`/buscar`, `/admin/personas`, moderation, delete) require `Depends(requiere_admin)`. Tests use the Bearer token fixture.
10. **Test coverage**: ≥80% line coverage on `app/domain/` and `app/repositories/`. `pytest` passes in CI.
11. **Cleanup**: v0 files (`load_image.py`, `search_image.py`, root `main.py`, `haarcascade_frontalface_default.xml`) are deleted. `CLAUDE.md` / `AGENTS.md` describe the current production stack.
12. **No behavioral regression in public shapes**: Existing public endpoint contracts (`/buscados`, `/encontrados`) return the same shapes; only the privacy-masked fields and `AlertaFamiliar` change for minors.

## Proposal question round — answered

The following questions were asked and answered:

- **Q1. Where should minor names live, and should admin see them?** → Store in DB; mask in ALL regular endpoints (public AND admin `/buscar`, `/admin/personas`). A future change (out of scope) may add a "super-admin with role" endpoint that bypasses the mask.
- **Q2. Should the cross-flow alert threshold differ from the ranking threshold?** → Same threshold. No separate alert threshold.
- **Q3. Should MatchingPolicy load calibration from a file?** → Python constants in the policy class, with the operational threshold wired from `config.py` Settings.
- **Q4. Should the percentage display stay with the `1.2` divisor?** → The `1.2` divisor is obsolete. The team replaced `pct_coincidencia` with `faces.distance_to_confidence`, a sigmoid calibrated for InsightFace buffalo_l. `MatchingPolicy.match_percentage` delegates to this function.
- **Q5. Which face model and detector should the domain adopt?** → InsightFace buffalo_l (ArcFace w600k_r50, 512-dim) with RetinaFace detector, as implemented by the team.
- **Q6. How should multi-embeddings per photo be handled?** → Each photo generates 1 base + up to 2 augmented embeddings (rotations ±15°), stored in `persona_embeddings`. Search uses `ROW_NUMBER() OVER (PARTITION BY p.person_id ...)` to pick the best match per person.
- **Q7. How should admin authentication work?** → `/admin/login` returns a Bearer token (`sha256("reencuentros::" + admin_password)`). All admin endpoints use `Depends(requiere_admin)`. Tests include the Bearer token fixture.
- **Q8. How should the moderation filter behave?** → Public searches always filter by `moderacion = 'aprobada'`. Admin can list by `moderacion=pendiente|rechazada|aprobada`. `PATCH /admin/personas/{id}/moderacion` updates the value.
