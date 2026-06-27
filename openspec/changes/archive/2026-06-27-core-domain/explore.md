# `core-domain` — Exploration Notes

**Phase**: sdd-explore
**Status**: ✅ complete
**Date**: 2026-06-26
**Change**: `core-domain`

---

## 1. Current state per candidate

### Candidate 3 — MatchingPolicy consolidation

**Where the friction lives today**

- `app/config.py:31` — `match_threshold: float = 0.50` is defined in pydantic-settings, but **it is never imported or used in `app/main.py`**. The application ignores its own configured threshold.
- `app/main.py:25-26` — Two hardcoded module-level constants:

  ```python
  CONF_ALTA = 0.40
  CONF_MEDIA = 0.50
  ```

- `app/main.py:33-37` — `nivel_confianza(d)` branches on `CONF_ALTA` and `CONF_MEDIA`:

  ```python
  def nivel_confianza(d: float) -> str:
      if d < CONF_ALTA:
          return "alta"
      if d < CONF_MEDIA:
          return "media"
      return "baja"
  ```

- `app/main.py:41-42` — `pct_coincidencia(d)` uses an undocumented `1.2` divisor:

  ```python
  def pct_coincidencia(d: float) -> int:
      return max(0, min(100, round((1 - d / 1.2) * 100)))
  ```

- `evaluate.py:34` — A separate threshold dictionary for benchmark purposes only:

  ```python
  THRESH = {"Facenet": 0.40, "Facenet512": 0.30, "ArcFace": 0.68, "SFace": 0.593, "VGG-Face": 0.68}
  ```

- `app/main.py:222` — The cross-flow alert in `registrar_encontrado` uses `d < CONF_MEDIA`, not `settings.match_threshold`:

  ```python
  if d < CONF_MEDIA:  # coincidencia real (alta/media)
      alerta = AlertaFamiliar(...)
  ```

- `POST /buscar` (admin, `app/main.py:230`) — Returns the top-N most similar rows **without any threshold filtering**. Every row gets a `confianza` string and a `coincidencia` percentage, but nothing is excluded for being too far.

**What "deepening" means here**

A single `MatchingPolicy` module that owns:

1. The numeric threshold(s) for "is this a match?"
2. The confidence-band mapping (`alta`/`media`/`baja`)
3. The percentage formula (`coincidencia`)
4. Whether the policy is consumed as "filter" (exclude rows) or "annotate" (label rows but keep them)

**Locality of knowledge**

| Today | After |
|-------|-------|
| Threshold intent is split between `config.py` (ignored), `main.py` constants, and `evaluate.py` | One policy object loaded from config or YAML |
| Confidence bands and percentage formula are inline in `main.py` | Policy module exports `confidence_band(distance) -> str` and `match_percentage(distance) -> int` |
| `/buscar` has no threshold logic; `/encontrados` has its own hardcoded check | Policy provides `is_match(distance) -> bool` used consistently by both flows |

**Direct dependencies on other candidates**

- Consumed by Candidate 5 (Persona): the Persona repository/query layer will need to ask the policy whether to filter or just annotate.
- Consumed by Candidate 6 (Menores privacy): the privacy serializer may need to know whether a match is strong enough before revealing certain fields.

---

### Candidate 5 — Persona domain object

**Where the friction lives today**

- `app/database.py:16-34` — The schema is built incrementally via `_EXTRA_COLS`, a list of `(col, decl)` tuples added with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. There is no single DDL source of truth.

  ```python
  _EXTRA_COLS = [
      ("person_id", "UUID"),
      ("estado", "TEXT NOT NULL DEFAULT 'buscada'"),
      ("es_menor", "BOOLEAN NOT NULL DEFAULT false"),
      ("nombre", "TEXT"),
      ...
  ]
  ```

- `app/schemas.py` — Two distinct Pydantic models that represent overlapping views of the same underlying person:
  - `Candidato` (search result, 14 fields)
  - `PersonaAdmin` (admin list, 13 fields)
  There is no base `Persona` model.
- `app/main.py:29` — A raw SQL column list `_SEL` is hardcoded as a module-level string:

  ```python
  _SEL = ("person_id, estado, es_menor, nombre, apellido, edad, refugio, ubicacion, "
          "telefono_responsable, telefono_contacto, descripcion, image_url")
  ```

- `app/main.py:74-91` — `_insertar_fotos` constructs a massive `INSERT` with 19 columns by hand, mapping a plain `dict` to SQL placeholders:

  ```python
  conn.execute(
      """
      INSERT INTO personas
        (id, person_id, estado, es_menor, nombre, apellido, edad, doc_tipo,
         doc_numero, telefono_contacto, refugio, telefono_responsable,
         doc_responsable, descripcion, ubicacion, codigo, image_url, image_key, embedding)
      VALUES (...)
      """,
      {**datos, "id": foto_id, "pid": person_id, "url": url, "key": key, "emb": embedding},
  )
  ```

- `app/main.py:93-101` — `_buscar_por_estado` embeds the same `_SEL` string into a `DISTINCT ON` subquery.
- `app/main.py:104-115` — `_fila_a_candidato` manually destructures the SQL row tuple into 13 positional variables and maps them into a `Candidato` model.
- `app/main.py:267-276` — The admin lister uses a completely different SQL aggregation (`max`, `bool_or`, `array_agg`, `coalesce`) with its own column order, and a separate inline mapping to `PersonaAdmin`.
- `estado` is `TEXT` with no CHECK constraint, no enum, and no Pydantic `Literal`. The only validation is the `in ("buscada", "encontrada")` guard in the endpoint handlers.

**What "deepening" means here**

A `Persona` domain object that represents "one logical person with N photos". It should:

1. Encapsulate the database access (insert, query by embedding, list, filter by estado)
2. Own the mapping from SQL row → domain object → Pydantic response model
3. Validate `estado` to only allow the two known values
4. Group rows by `person_id` and expose a `photos: list[str]` (URLs) instead of leaking the "one row per photo" implementation detail to every endpoint

**Locality of knowledge**

| Today | After |
|-------|-------|
| Schema definition in `_EXTRA_COLS`, SQL strings in `main.py`, Pydantic in `schemas.py` | `Persona` entity + repository in a dedicated module |
| Row-to-model mapping duplicated in `_fila_a_candidato` and `listar` | Single `from_row()` or repository method |
| `estado` validation scattered across endpoint parameter checks | Enum / Literal at the DB + schema + domain layer |

**Direct dependencies on other candidates**

- Consumes Candidate 3 (MatchingPolicy): the repository needs the policy to annotate `Candidato` results with `coincidencia` and `confianza`.
- Consumed by Candidate 6 (Menores privacy): the privacy serializer receives a `Persona` (or `Candidato`) and decides which fields to mask. If the domain object is well-defined, the privacy rule can be applied in one place after the model is built.

---

### Candidate 6 — Menores privacy protocol consolidation

**Where the friction lives today**

The rule "if `es_menor=True`, then `nombre` and `apellido` must NOT appear in API responses" is implemented in **three places**, and missing in a fourth:

1. `app/main.py:108-110` — `_fila_a_candidato`:

   ```python
   return Candidato(
       ...
       nombre=None if es_menor else nombre,
       apellido=None if es_menor else apellido,
       ...
   )
   ```

2. `app/main.py:207-209` — `registrar_encontrado` (before inserting into DB):

   ```python
   datos = dict(estado="encontrada", menor=es_menor,
                nombre=None if es_menor else nombre,
                apellido=None if es_menor else apellido,
                ...)
   ```

   Note: this nulls the name **before persistence**, meaning the DB itself stores `NULL` for minors. This is data loss — the original name submitted by the rescuer is discarded.
3. `frontend/index.html:137` — Frontend rendering layer:

   ```javascript
   const titulo=c.es_menor?'<i>Menor protegido</i>':((c.nombre||'')+' '+(c.apellido||'')).trim()||'<i>sin nombre</i>';
   ```

4. `frontend/index.html:194` — Admin search rendering also checks `c.es_menor`.

**Missing application:** `AlertaFamiliar` in `app/main.py:222-225` does **NOT** apply the protocol. When a rescuer registers a found person who matches a missing child, the alert exposes the child's name directly:

```python
alerta = AlertaFamiliar(
    person_id=str(r[0]), familiar_nombre=r[3], familiar_telefono=r[9],
    ...
)
```

`r[3]` is the raw `nombre` column from the SQL row, with no `es_menor` check.

**What "deepening" means here**

A single `MenoresPrivacy` serializer / policy that:

1. Receives a `Persona` or `Candidato` domain object
2. Returns a view with `nombre`/`apellido` nulled when `es_menor=True`
3. Is applied **once** at the API response boundary, not during DB insertion
4. Covers all endpoints including `AlertaFamiliar`

**Locality of knowledge**

| Today | After |
|-------|-------|
| Backend nulling in `_fila_a_candidato` and `registrar_encontrado` | One serializer/policy module |
| Frontend duplicating the nulling logic in two render functions | Frontend trusts backend; backend applies policy uniformly |
| `AlertaFamiliar` leaking minor names | Policy applied to all outgoing response models |

**Direct dependencies on other candidates**

- Consumes Candidate 5 (Persona): needs a stable `Persona`/`Candidato` object to transform.
- Consumed by Candidate 3 (MatchingPolicy) indirectly: if the admin endpoint starts filtering by threshold, the privacy serializer must still run on the remaining results.

---

## 2. Cleanup scope

| File | Size | Current role | Watch out for | References to clean |
|------|------|--------------|---------------|---------------------|
| `load_image.py` | 1,388 B | v0 prototype: ChromaDB loader using `Facenet` (not Facenet512) | None | `CLAUDE.md:33`, `AGENTS.md:33`, `.dockerignore:14` |
| `search_image.py` | 1,825 B | v0 prototype: ChromaDB searcher with hardcoded `< 1` cosine threshold | None | `CLAUDE.md:36`, `AGENTS.md:36`, `.dockerignore:15` |
| `main.py` (repo root) | 390 B | v0 scratchpad that imports the two classes above | **Do NOT delete `app/main.py`** — the production FastAPI lives there | `CLAUDE.md:27`, `AGENTS.md:27`, `.dockerignore:16` |
| `haarcascade_frontalface_default.xml` | 963 KB | OpenCV cascade file; never imported by current code | None | `CLAUDE.md:54`, `AGENTS.md:54`, `.dockerignore:13` |

**Anything to watch out for**

- The root `main.py` is the v0 scratchpad; `app/main.py` is the production API. The cleanup must target the root file only.
- `CLAUDE.md` and `AGENTS.md` (which is a symlink/copy of `CLAUDE.md`) describe the v0 architecture in detail. After deleting the files, these docs need a full rewrite to describe the current pgvector/Facenet512 stack, or they should be removed/deprecated.

---

## 3. Cross-cutting findings

1. **`match_threshold` in `config.py` is dead code**  
   `app/config.py:31` defines `match_threshold: float = 0.50`, but `app/main.py` never references it. The actual thresholds are the hardcoded `CONF_ALTA` and `CONF_MEDIA`. This means the documented "calibrated 0.50" threshold is not actually wired into the application logic.

2. **`ARQUITECTURA.md` drift**  
   `ARQUITECTURA.md` states the model is `SFace` with 128 dimensions and a threshold of `0.55`. The actual production stack (confirmed by `app/config.py`, `app/faces.py`, and `openspec/config.yaml`) is `Facenet512` with 512 dimensions and threshold `0.50`. This doc is dangerously misleading for ops.

3. **`AlertaFamiliar` privacy leak (bug)**  
   As noted in Candidate 6, the cross-flow alert does not apply the menores protocol. A rescuer who registers a found child will receive the child's real name in the alert payload. This is a live privacy bug, not just technical debt.

4. **`app/faces.py` docstring drift**  
   The module docstring says `"modelo Facenet por defecto"`, but the code reads `s.face_model` (which is `Facenet512` in production). Minor but contributes to confusion.

5. **`estado` is free TEXT everywhere**  
   No CHECK constraint in the DB, no `Literal["buscada", "encontrada"]` in Pydantic, no enum in Python. Existing rows could contain typos or unexpected values.

6. **No tests** (from init report, re-confirmed)  
   Zero test files, zero pytest config. Any refactoring of core-domain logic is completely unguarded.

---

## 4. Specific code patterns to extract

### A. Matching policy (confidence + percentage)

- **Current:** `app/main.py:25-42`
- **What it does:** Defines `CONF_ALTA`, `CONF_MEDIA`, `nivel_confianza()`, `pct_coincidencia()`
- **New home:** `app/domain/matching.py` or `app/policies/matching.py`
- **Future interface:**

  ```python
  class MatchingPolicy:
      def is_match(self, distance: float) -> bool: ...
      def confidence_band(self, distance: float) -> Literal["alta", "media", "baja"]: ...
      def match_percentage(self, distance: float) -> int: ...
  ```

### B. Privacy serializer for minors

- **Current:** `app/main.py:108-110` and `app/main.py:207-209` (and the missing `AlertaFamiliar` fix)
- **What it does:** Nulls `nombre`/`apellido` when `es_menor=True`
- **New home:** `app/domain/privacy.py` or `app/serializers/privacy.py`
- **Future interface:**

  ```python
  def apply_menores_privacy(persona: Persona | Candidato) -> Persona | Candidato: ...
  ```

### C. Persona repository / query builder

- **Current:** `app/main.py:29` (`_SEL`), `app/main.py:74-91` (`_insertar_fotos`), `app/main.py:93-101` (`_buscar_por_estado`), `app/main.py:267-276` (admin lister)
- **What it does:** All SQL execution and row-to-model mapping for the `personas` table
- **New home:** `app/repositories/persona.py`
- **Future interface:**

  ```python
  class PersonaRepository:
      def add(self, person: Persona, photos: list[Photo]) -> list[str]: ...  # returns URLs
      def search_by_estado(self, embedding, estado, limit) -> list[Candidato]: ...
      def list_all(self, limit, estado=None) -> list[PersonaAdmin]: ...
  ```

### D. Persona domain entity + factory

- **Current:** Implicit in `app/main.py:166` and `app/main.py:207` (plain `dict` construction)
- **What it does:** Gathers form fields into a `dict` that is later exploded into SQL placeholders
- **New home:** `app/domain/persona.py`
- **Future interface:**

  ```python
  @dataclass
  class Persona:
      person_id: UUID
      estado: Literal["buscada", "encontrada"]
      es_menor: bool
      nombre: str | None
      ...
  ```

---

## 5. Risks specific to this change

1. **Undocumented `1.2` divisor in `pct_coincidencia`**  
   Moving this formula into a policy module might surface a hidden bug. No one knows why `1.2` was chosen. If the model or detector changes, this number may be wrong. It needs to be recalibrated or documented.

2. **Cross-flow alert threshold mismatch**  
   `registrar_encontrado` uses `d < CONF_MEDIA` (0.50) for the alert, while `config.py` defines `match_threshold=0.50`. They happen to match numerically, but conceptually the alert may need a stricter threshold than the ranking list. Consolidating them without understanding the product intent could cause missed alerts or false positives.

3. **DB schema evolution with production data**  
   Adding a CHECK constraint on `estado` or changing column defaults requires care. `app/database.py` already uses `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, so the migration pattern exists, but adding CHECK constraints on existing tables can fail if bad data exists.

4. **`estado` as free TEXT → migration risk**  
   If we introduce an enum or CHECK constraint, any existing row with a non-standard `estado` value will break `init_db()` or future inserts. A data audit is needed before enforcing the constraint.

5. **Menores privacy nulls data before persistence**  
   `registrar_encontrado` currently sets `nombre=None` **before** inserting into the DB. If we move the privacy rule to the serializer layer (apply on response only), we would start storing the real name in the DB. This is architecturally correct but changes the data model: the DB would now contain minor names. The admin endpoint (`/admin/personas`) today returns `nombre` directly from the DB without nulling it, so admins already see names if they look at the DB. But if the product intent is "never store the name," the serializer-only approach would violate that.

6. **`/buscar` admin endpoint does not apply privacy protocol today**  
   The admin search returns `_fila_a_candidato`, which *does* null names for minors. But the frontend admin tab also has its own `es_menor` check. Consolidating to a single backend serializer changes the wire format subtly: if today the backend sometimes sends the name and the frontend hides it, moving all nulling to the backend makes the contract cleaner but must be verified.

7. **Zero tests**  
   Every extraction (MatchingPolicy, Persona repository, privacy serializer) is a refactor with no safety net. The only validation is manual endpoint testing.

---

## 6. Open questions for the proposal question round

1. **Admin visibility of minor names**  
   The `/buscar` admin endpoint currently returns `Candidato` objects, which do null minor names. But the admin lister (`/admin/personas`) returns `PersonaAdmin` with `nombre` and `apellido` straight from the DB — no nulling. Should the menores privacy protocol apply to **all** API responses (including admin), or do admins have a legitimate need to see a minor's real name for coordination with authorities?

2. **Alert threshold vs. ranking threshold**  
   The cross-flow alert (`registrar_encontrado`) uses the same numeric threshold as the confidence-band boundary (`CONF_MEDIA = 0.50`). Should the alert that notifies a rescuer "a family is looking for this person" require a **higher** confidence than the general ranking list? In other words, is it acceptable to show a "media" match to a user browsing results, but only send a real-time alert for "alta" matches?

3. **Where should minor names live?**  
   Today, `registrar_encontrado` discards the minor's name before writing to the database (sets `nombre=None`). This means the name is lost forever. Is the product rule "never store a minor's name," or is it "store it but never expose it in public-facing APIs"? The answer determines whether the privacy protocol belongs in the serializer layer or the persistence layer.

4. **Calibration source for MatchingPolicy**  
   The current threshold (`0.50`) was calibrated for Facenet512 on a specific real-world test set (same-person ≤0.469, different-people ≥0.549). Should the new `MatchingPolicy` load its thresholds from a YAML/JSON file that can be updated without a code deployment, or should they remain hardcoded Python constants? A file would help ops tune in production; constants are simpler but require a deploy to change.

5. **Percentage formula ownership**  
   The `pct_coincidencia` formula (`round((1 - d / 1.2) * 100)`) is undocumented and model-dependent. Should the percentage even be part of the MatchingPolicy, or should it be removed entirely and replaced with raw distance + confidence band? If families are shown a "87%" number, it creates a false sense of mathematical precision that may not hold across photo quality, lighting, or detector variance.
