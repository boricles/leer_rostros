# `core-domain` — Domain Specification

## Purpose

This specification defines the core domain behaviors that the Reencuentros service MUST exhibit after this change. It covers four concerns: (1) a unified **matching policy** that consolidates all threshold, confidence-band, and percentage-formula decisions into a single source of truth, now delegating to the sigmoid in `faces.distance_to_confidence` calibrated for InsightFace buffalo_l; (2) a first-class **Persona** entity with a dedicated repository that owns all SQL for the `personas` and `persona_embeddings` tables, including multi-embedding support per photo; (3) a **menores privacy** protocol that protects minors' identities at the API response boundary for ALL regular endpoints (public AND admin), without discarding data before persistence; and (4) **admin authentication** via Bearer token for all admin endpoints. The specification also requires a moderation filter on public searches, removal of v0 prototype files, and establishment of a pytest test infrastructure.

## Requirements

### Matching

#### Requirement: Single source of truth for match threshold

The system MUST provide a `MatchingPolicy` module as the single source of truth for all match-threshold, confidence-band, and percentage-formula decisions. The operational threshold MUST be loaded from `Settings.match_threshold` (defined in `config.py`, default `0.55`). Confidence bands (`CONF_ALTA`, `CONF_MEDIA`) MUST be defined as constants within or alongside the `MatchingPolicy` module, calibrated for InsightFace buffalo_l.

#### Scenario: Wired threshold takes effect

- GIVEN `Settings.match_threshold = 0.55`
- WHEN a search returns a row with cosine distance `0.45`
- THEN `MatchingPolicy.is_match(0.45)` returns `True`
- AND `MatchingPolicy.confidence_band(0.45)` returns `"media"`

#### Scenario: Confidence bands respect thresholds

- GIVEN `Settings.match_threshold = 0.55`, `CONF_ALTA = 0.40`, `CONF_MEDIA = 0.55`
- WHEN `MatchingPolicy.confidence_band` is called with distances `0.30`, `0.45`, `0.60`
- THEN it returns `"alta"`, `"media"`, `"baja"` respectively

#### Scenario: Non-matching distance returns False

- GIVEN `Settings.match_threshold = 0.55`
- WHEN `MatchingPolicy.is_match(0.60)` is called
- THEN it returns `False`

#### Requirement: Percentage formula uses sigmoid from `faces.distance_to_confidence`

The system MUST provide a `MatchingPolicy.match_percentage(distance)` method that computes a 0–100 integer percentage from the cosine distance by delegating to `faces.distance_to_confidence`. The sigmoid is calibrated for InsightFace buffalo_l with `confidence_sigmoid_k=12.0` (slope) and `confidence_sigmoid_midpoint=0.40` (distance where confidence = 50%). The implementation MUST include a code comment documenting that the sigmoid replaces the old `1.2` divisor (which was calibrated for Facenet512 + retinaface and is no longer applicable).

Typical values with the sigmoid:

- distance 0.10 → ~97% (match very clear)
- distance 0.25 → ~85% (solid match)
- distance 0.40 → ~50% (uncertainty point)
- distance 0.55 → ~16% (at threshold — review manually)

#### Scenario: Percentage calculation with sigmoid

- GIVEN the sigmoid formula with `k=12.0` and `midpoint=0.40`
- WHEN `match_percentage` is called with distance `0.36`
- THEN it returns `62` (i.e., `round(100 / (1 + exp(12.0 * (0.36 - 0.40)))) ≈ round(100 / 1.6188) ≈ 62`)

#### Scenario: Percentage is clamped to [0, 100]

- GIVEN the sigmoid formula
- WHEN `match_percentage` is called with distance `2.0`
- THEN it returns a value close to `0` (sigmoid asymptote)
- WHEN `match_percentage` is called with distance `0.0`
- THEN it returns `100` (sigmoid maximum)

#### Requirement: Cross-flow alert and ranking list share the same threshold

The `AlertaFamiliar` flow (triggered during `POST /encontrados` registration) and the ranking list returned by `POST /buscados` and `POST /buscar` MUST both consult the same `MatchingPolicy.is_match()` method to determine whether a distance qualifies as a match. There MUST NOT be a separate `alert_threshold` or `display_threshold` constant anywhere in the production code.

#### Scenario: Alert uses same threshold as search

- GIVEN `Settings.match_threshold = 0.55` and a found person whose best match has distance `0.48`
- WHEN `registrar_encontrado` evaluates whether to create an `AlertaFamiliar`
- THEN `MatchingPolicy.is_match(0.48)` returns `True` and the alert is generated

#### Scenario: No alert below threshold

- GIVEN `Settings.match_threshold = 0.55` and a found person whose best match has distance `0.60`
- WHEN `registrar_encontrado` evaluates whether to create an `AlertaFamiliar`
- THEN `MatchingPolicy.is_match(0.60)` returns `False` and no alert is generated

#### Requirement: Benchmark thresholds are isolated from production

The `evaluate.py` benchmark script MAY retain its own `THRESH` dictionary for model-comparison purposes. This dictionary MUST NOT be imported or referenced by any file under `app/`. The `MatchingPolicy` module MUST NOT depend on `evaluate.py`.

### Persona

#### Requirement: Persona is a first-class entity

The system MUST represent a registered person as a `Persona` domain object that encapsulates its `person_id`, `estado`, `es_menor`, `nombre`, `apellido`, and associated photo URLs. The `Persona` object MUST be a Python dataclass or Pydantic model. The system MUST validate that `estado` is one of `"buscada"` or `"encontrada"` at construction or serialization time.

#### Scenario: New persona carries photos

- GIVEN a registration request with 3 photos and `estado="encontrada"`
- WHEN the use case constructs a `Persona`
- THEN `persona.photos` has length 3
- AND `persona.estado == "encontrada"`

#### Scenario: Invalid estado is rejected

- GIVEN a request with `estado="desconocida"`
- WHEN the system attempts to construct a `Persona`
- THEN it raises a validation error

#### Requirement: PersonaRepository owns all SQL for the personas and persona_embeddings tables

The system MUST provide a `PersonaRepository` class that encapsulates all SQL queries, inserts, and updates for the `personas` and `persona_embeddings` tables. No raw SQL strings for the `personas` or `persona_embeddings` tables MAY remain in `app/main.py`. The repository MUST handle row-to-model mapping via a centralized method (e.g., `from_row()` or equivalent).

#### Scenario: Repository returns typed Persona objects

- GIVEN a database query for personas with `estado="buscada"`
- WHEN `PersonaRepository.search_by_estado(embedding, "buscada", limit=10)` is called
- THEN it returns a list of `Persona` or `Candidato` objects, not raw tuples or dicts

#### Scenario: No raw SQL in app/main.py

- GIVEN a freshly built codebase
- WHEN `app/main.py` is scanned for SQL strings referencing the `personas` or `persona_embeddings` tables
- THEN no `SELECT`, `INSERT`, or `UPDATE` strings targeting these tables are found

#### Requirement: Persona handles multi-embeddings per photo

The repository MUST support N embeddings per photo stored in the `persona_embeddings` table (1 base + up to 2 augmented embeddings from rotations ±15°). Search queries MUST use `ROW_NUMBER() OVER (PARTITION BY p.person_id ORDER BY pe.embedding <=> %s ASC)` to get the best match per person across all embeddings. Multiple embeddings for the same photo MUST be inserted atomically alongside the photo row.

#### Scenario: Search returns best match per person across multiple embeddings

- GIVEN a person with 2 photos, each having 3 embeddings (base + 2 rotations) = 6 total embeddings
- WHEN `PersonaRepository.search_by_estado` is called with a query embedding
- THEN the result includes at most 1 row for that person, using the closest embedding
- AND the `distancia` returned is the minimum across all 6 embeddings

#### Scenario: Multi-embeddings are inserted per photo

- GIVEN a registration with 1 photo that yields 3 embeddings (base + 2 rotations)
- WHEN the persona is persisted
- THEN 1 row is inserted into `personas` and 3 rows into `persona_embeddings`

#### Requirement: Row-to-model mapping is centralized

The system MUST provide a single method (in the repository or a factory) that converts a raw database row into a `Persona` or `Candidato` object. This method MUST handle all field mappings including `person_id`, `estado`, `es_menor`, `nombre`, `apellido`, `edad`, `refugio`, `ubicacion`, `telefono_responsable`, `telefono_contacto`, `descripcion`, and `image_url`. Multiple photos for the same `person_id` MUST be aggregated into a single `Persona.photos` list.

#### Scenario: Multiple photos grouped by person_id

- GIVEN 3 database rows with the same `person_id` but different `image_url` values
- WHEN the repository maps these rows
- THEN a single `Persona` object is produced with `photos` containing all 3 URLs

#### Requirement: Menores names are stored, not nulled, before persistence

The system MUST store the submitted `nombre` and `apellido` values in the database for all persons, including minors. The system MUST NOT set `nombre=None` or `apellido=None` before inserting into the database when `es_menor=True`. Privacy masking MUST occur only at the API response boundary (see Privacy section).

#### Scenario: Minor name preserved in database

- GIVEN a registration request with `es_menor=True`, `nombre="Juan"`, `apellido="Pérez"`
- WHEN the persona is persisted
- THEN the database row contains `nombre="Juan"` and `apellido="Pérez"`

#### Requirement: Persona repository filters public searches by `moderacion='aprobada'`

All public search queries (those not requiring admin authentication) MUST include `moderacion = 'aprobada'` in their WHERE clause. Personas with `moderacion='rechazada'` or `moderacion='pendiente'` MUST NOT appear in public search results.

#### Scenario: Rechazada personas do not appear in public results

- GIVEN a persona with `moderacion='rechazada'` and a matching embedding
- WHEN a public search (`POST /buscados` or `POST /encontrados` cross-flow) is performed
- THEN that persona is NOT included in the results

#### Scenario: Pendiente personas do not appear in public results

- GIVEN a persona with `moderacion='pendiente'` and a matching embedding
- WHEN a public search (`POST /buscados` or `POST /encontrados` cross-flow) is performed
- THEN that persona is NOT included in the results

### Privacy

#### Requirement: Menores privacy applied to ALL regular API responses

The system MUST mask `nombre` and `apellido` to `None` for any `Persona` or `Candidato` with `es_menor=True` that is returned by ANY regular endpoint — public (`POST /buscados`, `GET /encontrados`) AND admin (`POST /buscar`, `GET /admin/personas`). The masking MUST be applied at the response-serialization boundary, not before database insertion. A future special "super-admin with role" endpoint that bypasses this mask is out of scope for this change.

#### Scenario: Public search masks minor name

- GIVEN a `Candidato` with `es_menor=True`, `nombre="Juan"`, `apellido="Pérez"`
- WHEN the `POST /buscados` endpoint returns the `Candidato` to the familiar
- THEN the response has `nombre=None` and `apellido=None`

#### Scenario: Cross-flow response masks minor name

- GIVEN a `Candidato` with `es_menor=True`, `nombre="María"`, `apellido="García"`
- WHEN the `POST /encontrados` endpoint returns a `Candidato` to the rescuer
- THEN the response has `nombre=None` and `apellido=None`

#### Scenario: Admin search masks minor name

- GIVEN a `Candidato` with `es_menor=True`, `nombre="Juan"`, `apellido="Pérez"`
- WHEN the `POST /buscar` endpoint returns the `Candidato` to the admin
- THEN the response has `nombre=None` and `apellido=None`

#### Scenario: Admin list masks minor name

- GIVEN a `PersonaAdmin` with `es_menor=True`, `nombre="María"`, `apellido="García"`
- WHEN the `GET /admin/personas` endpoint returns the `PersonaAdmin` to the admin
- THEN the response has `nombre=None` and `apellido=None`

#### Requirement: Menores privacy is applied in regular admin endpoints; super-admin role bypass is out of scope

The system MUST apply the same menores masking in regular admin endpoints (`POST /buscar`, `GET /admin/personas`) as it does in public endpoints. A future change (out of scope for this SDD) may introduce a "super-admin with role" endpoint that bypasses the mask. This change does NOT implement that bypass.

#### Requirement: AlertaFamiliar respects menores privacy

The `AlertaFamiliar` response embedded in the `POST /encontrados` response MUST apply the menores privacy protocol. When the matched person has `es_menor=True`, the `familiar_nombre` field in the `AlertaFamiliar` response MUST be `None`. When `es_menor=False`, `familiar_nombre` MUST contain the real name from the database (no regression). This is a bug fix for a live privacy leak.

#### Scenario: AlertaFamiliar masks minor name

- GIVEN a matched `Persona` with `es_menor=True` and `nombre="Ana"`
- WHEN the `POST /encontrados` response includes an `AlertaFamiliar`
- THEN the alert's `familiar_nombre` is `None`

#### Scenario: AlertaFamiliar preserves non-minor name

- GIVEN a matched `Persona` with `es_menor=False` and `nombre="Carlos"`
- WHEN the `POST /encontrados` response includes an `AlertaFamiliar`
- THEN the alert's `familiar_nombre` is `"Carlos"`

#### Requirement: MenoresPrivacy is a single callable

The system MUST provide a single `MenoresPrivacy` callable (function or class) in `app/domain/privacy.py` that takes a `Persona`, `Candidato`, `PersonaAdmin`, or `AlertaFamiliar` and returns a copy (or transformed view) with `nombre`/`apellido`/`familiar_nombre` set to `None` when `es_menor=True`. Endpoint handlers MUST invoke this callable to decide whether to apply masking.

#### Scenario: MenoresPrivacy returns a masked copy

- GIVEN a `Candidato(es_menor=True, nombre="Luis", apellido="Díaz")`
- WHEN `MenoresPrivacy(candidate)` is called
- THEN the returned object has `nombre=None` and `apellido=None`
- AND the original object is unchanged

#### Scenario: MenoresPrivacy passes through non-minor

- GIVEN a `Candidato(es_menor=False, nombre="Rosa", apellido="López")`
- WHEN `MenoresPrivacy(candidate)` is called
- THEN the returned object has `nombre="Rosa"` and `apellido="López"`

#### Scenario: MenoresPrivacy masks AlertaFamiliar

- GIVEN an `AlertaFamiliar` built from a match where `es_menor=True` and `familiar_nombre="Ana"`
- WHEN `MenoresPrivacy(alert)` is called
- THEN the returned alert has `familiar_nombre=None`

#### Requirement: Frontend no longer applies its own nulling logic

The frontend (`frontend/index.html`) MUST NOT contain JavaScript logic that nulls or masks `nombre` or `apellido` based on `es_menor`. The frontend MUST trust the backend to have already applied the menores privacy protocol to all regular API responses.

#### Scenario: Frontend renders received names as-is

- GIVEN the backend returns a public response with `nombre=None` for a minor
- WHEN the frontend renders the candidate card
- THEN it displays a placeholder (e.g., "Menor protegido") based on the `None` value it received

### Auth

#### Requirement: Admin endpoints require Bearer token

All admin endpoints (`POST /buscar`, `GET /admin/personas`, `PATCH /admin/personas/{id}/moderacion`, `DELETE /admin/personas/{id}`) MUST require a valid Bearer token via `Authorization` header. Requests without a valid token MUST return HTTP 401. The `/admin/login` endpoint MUST NOT require authentication and MUST return a token when valid credentials are provided.

#### Scenario: Admin login returns token

- GIVEN valid credentials (`usuario="admin"`, `password=Settings.admin_password`)
- WHEN `POST /admin/login` is called with those credentials
- THEN it returns a `LoginResp` with `token=sha256("reencuentros::" + admin_password)` and `tipo="Bearer"`

#### Scenario: Authenticated admin can access /admin/personas

- GIVEN a valid Bearer token obtained from `/admin/login`
- WHEN `GET /admin/personas` is called with `Authorization: Bearer <token>`
- THEN the request succeeds and returns a list of `PersonaAdmin` objects

#### Scenario: Unauthenticated request to /admin/personas returns 401

- GIVEN no `Authorization` header
- WHEN `GET /admin/personas` is called
- THEN it returns HTTP 401

#### Requirement: Bearer token is validated against Settings.admin_password

The token validation function (`requiere_admin`) MUST compare the incoming `Authorization` header against `Bearer {sha256("reencuentros::" + Settings.admin_password)}`. An invalid or missing token MUST raise HTTP 401.

#### Scenario: Valid token grants access

- GIVEN `Settings.admin_password = "reencuentros2026"`
- WHEN a request includes `Authorization: Bearer {sha256("reencuentros::reencuentros2026")}`
- THEN `requiere_admin` allows the request to proceed

#### Scenario: Invalid token returns 401

- GIVEN `Settings.admin_password = "reencuentros2026"`
- WHEN a request includes `Authorization: Bearer wrongtoken`
- THEN `requiere_admin` raises HTTP 401

### Moderation

#### Requirement: Public searches filter by `moderacion='aprobada'`

All public-facing search queries (`POST /buscados`, the cross-flow alert in `POST /encontrados`) MUST include `moderacion = 'aprobada'` in their SQL WHERE clause. Personas with any other moderation status MUST NOT appear in public results.

#### Scenario: Rechazada personas do not appear in /buscados results

- GIVEN a persona with `moderacion='rechazada'` and an embedding that matches the query
- WHEN `POST /buscados` is called
- THEN that persona is NOT in the returned `coincidencias` list

#### Scenario: Pendiente personas do not appear in cross-flow alerts

- GIVEN a persona with `moderacion='pendiente'` and an embedding that matches the query in `POST /encontrados`
- WHEN the cross-flow alert logic runs
- THEN no `AlertaFamiliar` is generated for that persona

#### Requirement: Admin can list by moderacion status

The `GET /admin/personas` endpoint MUST support optional filtering by `moderacion` status (`aprobada`, `rechazada`, `pendiente`). When no filter is provided, all personas are returned regardless of moderation status.

#### Scenario: Admin can list pendientes for review

- GIVEN 3 personas with `moderacion='pendiente'` and 5 with `moderacion='aprobada'`
- WHEN `GET /admin/personas?moderacion=pendiente` is called
- THEN the response contains exactly the 3 pending personas

#### Requirement: PATCH /admin/personas/{id}/moderacion updates status

The endpoint `PATCH /admin/personas/{person_id}/moderacion?valor={status}` MUST update the `moderacion` column for all rows sharing the given `person_id`. The `valor` parameter MUST be one of `aprobada`, `rechazada`, or `pendiente`. Invalid values MUST return HTTP 400. Non-existent `person_id` MUST return HTTP 404.

#### Scenario: Admin approves a pendiente

- GIVEN a persona with `moderacion='pendiente'`
- WHEN `PATCH /admin/personas/{id}/moderacion?valor=aprobada` is called with a valid Bearer token
- THEN the persona's `moderacion` is updated to `'aprobada'` and it appears in public searches

#### Scenario: Admin rejects a pendiente

- GIVEN a persona with `moderacion='pendiente'`
- WHEN `PATCH /admin/personas/{id}/moderacion?valor=rechazada` is called with a valid Bearer token
- THEN the persona's `moderacion` is updated to `'rechazada'` and it does NOT appear in public searches

#### Scenario: Invalid moderacion value returns 400

- WHEN `PATCH /admin/personas/{id}/moderacion?valor=invalido` is called
- THEN it returns HTTP 400 with an error message

### Cleanup

#### Requirement: v0 prototype files removed

The system MUST NOT contain the following v0 ChromaDB prototype files at the repository root:

- `load_image.py`
- `search_image.py`
- `main.py` (repo root, NOT `app/main.py`)
- `haarcascade_frontalface_default.xml`

#### Scenario: Repo does not contain v0 files

- GIVEN a clean clone of the repo after this change
- WHEN the files `load_image.py`, `search_image.py`, `main.py` (root), and `haarcascade_frontalface_default.xml` are checked
- THEN none of these files exist

#### Requirement: Documentation reflects current production stack

`CLAUDE.md` and `AGENTS.md` MUST describe the current production stack (pgvector, InsightFace buffalo_l, FastAPI) and MUST NOT reference ChromaDB, the v0 `LoadImage`/`SearchImage` classes, or the `database/` ChromaDB persistence directory.

#### Scenario: CLAUDE.md is current

- GIVEN the documentation after this change
- WHEN `CLAUDE.md` is read
- THEN it mentions `pgvector`, `InsightFace buffalo_l`, and `FastAPI`
- AND it does NOT mention `chromadb`, `LoadImage`, or `SearchImage`

#### Scenario: AGENTS.md is current

- GIVEN the documentation after this change
- WHEN `AGENTS.md` is read
- THEN it mentions `pgvector`, `InsightFace buffalo_l`, and `FastAPI`
- AND it does NOT mention `chromadb`, `LoadImage`, or `SearchImage`

#### Requirement: Repository uses sigmoid for confidence

Documentation and code comments MUST reference `faces.distance_to_confidence` as the canonical confidence calculation. The old `1.2` divisor formula MUST NOT appear in any active code path or documentation.

#### Requirement: Auth is consistent across admin endpoints

All admin endpoints (`/buscar`, `/admin/personas`, moderation, delete) MUST use `Depends(requiere_admin)`. Tests MUST verify that each admin endpoint returns 401 without a valid Bearer token.

### Test Infrastructure

#### Requirement: pytest infrastructure in place

The repository MUST include a working pytest setup:

- `pytest` listed in a dev-requirements file (or a `requirements-dev.txt` file)
- A `conftest.py` with at least the bare minimum setup for `from app...` imports to work
- At least one test file under `tests/` that exercises the new domain modules

#### Scenario: pytest discovers tests

- GIVEN a clean install of dev requirements
- WHEN `pytest` is run from the repository root
- THEN it discovers at least the `tests/domain/test_matching.py` and `tests/domain/test_privacy.py` files
- AND all tests pass

#### Requirement: MatchingPolicy has unit tests

The `MatchingPolicy` module MUST have unit tests under `tests/domain/test_matching.py` that cover:

- `is_match` with distances above, below, and equal to the threshold
- `confidence_band` for all three bands (`alta`, `media`, `baja`)
- `match_percentage` sigmoid behavior with typical distances

#### Scenario: MatchingPolicy tests pass

- GIVEN the `tests/domain/test_matching.py` file exists
- WHEN `pytest tests/domain/test_matching.py` is run
- THEN all tests pass

#### Requirement: MenoresPrivacy has unit tests

The `MenoresPrivacy` callable MUST have unit tests under `tests/domain/test_privacy.py` that cover:

- Masking when `es_menor=True`
- No masking when `es_menor=False`
- Original object immutability (copy returned, not mutated)
- `AlertaFamiliar.familiar_nombre` masking for minors

#### Scenario: MenoresPrivacy tests pass

- GIVEN the `tests/domain/test_privacy.py` file exists
- WHEN `pytest tests/domain/test_privacy.py` is run
- THEN all tests pass

#### Requirement: Auth tests use Bearer token fixture

The test suite MUST provide a Bearer token fixture in `conftest.py` that computes `sha256("reencuentros::" + admin_password)` for use in admin endpoint tests. All admin endpoint tests MUST use this fixture.

#### Scenario: conftest.py provides a Bearer token fixture for admin tests

- GIVEN the `conftest.py` file
- WHEN it is inspected for auth-related fixtures
- THEN it provides a fixture that yields a valid `Authorization: Bearer <token>` header value

#### Requirement: Repository tests cover multi-embeddings

Repository tests MUST verify that `search_by_estado` returns the best match per person when multiple embeddings exist for the same photo.

#### Scenario: search_by_estado returns the best match per person across multiple embeddings

- GIVEN a person with 1 photo having 3 embeddings at distances 0.50, 0.35, 0.42 from the query
- WHEN `search_by_estado` is called
- THEN the result includes that person with `distancia=0.35` (the best of the 3)
