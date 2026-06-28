# Use-Case Layer Specification

## Purpose

This specification defines the use-case layer that sits between FastAPI endpoints and the domain/repository layers in the reencuentros service. The service is organized as **bounded contexts** (`personas`, `reportes`), each with its own `repositories/` and `use_cases/` subpackages, sharing common infrastructure from `app/shared/` (domain exceptions and helpers). After this change, each business flow has a single, named use-case class that encapsulates validation, domain-object construction, repository orchestration, privacy application, and response assembly. Endpoints in `app/main.py` become thin HTTP adapters (≤20 lines) that parse requests, call the use case's `execute` method, catch domain exceptions, and map them to HTTP status codes. The `PersonaBase` domain object flows through the system instead of being bypassed by raw dicts, and the use-case layer becomes independently testable with in-memory fakes.

## Requirements

### Bounded Contexts

#### Requirement: Bounded context organization

The system MUST organize its data-access and orchestration code into bounded contexts at the top of the `app/` package:

- `app/personas/repositories/` — `PersonaRepository` (SQL for `personas` + `persona_embeddings`).
- `app/personas/use_cases/` — six use-case classes for the personas flows (see [Use Case Module](#requirement-one-use-case-class-per-flow)).
- `app/reportes/repositories/` — `ReporteRepository` (SQL for `reportes`).
- `app/reportes/use_cases/` — four use-case classes for the reportes flows (see [Use Case Module](#requirement-one-use-case-class-per-flow)).
- `app/shared/` — domain exceptions and helpers used by every bounded context.

#### Scenario: Top-level package layout

- GIVEN the project is built
- WHEN the `app/` package is listed
- THEN there are top-level subpackages `domain/`, `shared/`, `personas/`, and `reportes/`
- AND `personas/` and `reportes/` each contain `repositories/` and `use_cases/` subpackages
- AND there is NO top-level `app/repositories/` or `app/use_cases/` directory

### Use Case Module

#### Requirement: One use case class per flow

The system MUST provide one use case class per business flow, distributed across the two bounded contexts:

**Bounded context `personas` (`app/personas/use_cases/`):**

- `RegistrarBusqueda` — FAMILIAR flow (`POST /buscados`)
- `RegistrarEncontrado` — RESCATISTA flow (`POST /encontrados`)
- `BuscarAdmin` — ADMIN photo search (`POST /buscar`)
- `ListarPersonasAdmin` — ADMIN list (`GET /admin/personas`)
- `ModerarPersona` — ADMIN moderation (`PATCH /admin/personas/{id}/moderacion`)
- `EliminarPersona` — ADMIN delete (`DELETE /admin/personas/{id}`)

**Bounded context `reportes` (`app/reportes/use_cases/`):**

- `RegistrarFalla` — Public report of a website bug (`POST /reportes/falla`)
- `RegistrarPublicacion` — Public report of an inadequate publication (`POST /reportes/publicacion`)
- `ListarReportesAdmin` — ADMIN list of reports (`GET /admin/reportes`)
- `CambiarEstadoReporte` — ADMIN moderation of a report's status (`PATCH /admin/reportes/{id}/estado`)

`admin_login` (`POST /admin/login`) MUST remain in `app/main.py` and MUST NOT be extracted into a use case.

`GET /health` MUST remain as a direct endpoint and MUST NOT have a use case.

#### Scenario: Bounded-context directory structure

- GIVEN the project is built
- WHEN the `app/personas/use_cases/` and `app/reportes/use_cases/` directories are listed
- THEN each contains one Python file per use case class plus an `__init__.py` barrel

#### Scenario: Each use case has a single execute method

- GIVEN a use case class (e.g., `RegistrarBusqueda`)
- WHEN it is instantiated with its dependencies (`PersonaRepository` for personas; `ReporteRepository` for reportes; `MatchingPolicy` as applicable)
- THEN it exposes a public `execute(...)` method that performs the full flow and returns a Pydantic response model or response-shaped dict

### Endpoint Thinness

#### Requirement: Endpoints are HTTP adapters

Each endpoint function in `app/main.py` that delegates to a use case MUST be at most 20 lines and MUST contain only:

1. Request parsing (form data, query params, path params, file uploads)
2. Face-processing calls (`_procesar_fotos`, `_embedding_consulta`) at the HTTP boundary
3. Use case instantiation and `execute(...)` invocation inside a `try/except` block
4. Domain exception catching and mapping to `HTTPException` with the appropriate status code
5. Return of the Pydantic response model from the use case

The endpoint MUST NOT contain business logic, validation rules, `PersonaBase` construction, repository calls, `MenoresPrivacy` application, `MatchingPolicy` calls, `AlertaFamiliar` construction, or response field assembly.

#### Scenario: Endpoint for POST /buscados

- GIVEN a `POST /buscados` request with valid form data and uploaded files
- WHEN the request is processed
- THEN the endpoint parses the form, calls `_procesar_fotos`, instantiates `RegistrarBusqueda`, calls `execute(...)`, and returns the `ResultadoBusqueda`
- AND the endpoint body is at most 20 lines of code

#### Scenario: Endpoint for POST /encontrados

- GIVEN a `POST /encontrados` request with valid form data and uploaded files
- WHEN the request is processed
- THEN the endpoint parses the form, calls `_procesar_fotos`, instantiates `RegistrarEncontrado`, calls `execute(...)`, and returns the `ResultadoRegistro`
- AND the endpoint body is at most 20 lines of code

### Use Case Return Type

#### Requirement: Use cases return Pydantic response models

Each use case's `execute` method MUST return the same Pydantic response model (or response-shaped dict) that the corresponding endpoint returns:

| Use case | Return type |
|---|---|
| `RegistrarBusqueda.execute` | `ResultadoBusqueda` |
| `RegistrarEncontrado.execute` | `ResultadoRegistro` |
| `BuscarAdmin.execute` | `list[Candidato]` |
| `ListarPersonasAdmin.execute` | `list[PersonaAdmin]` |
| `ModerarPersona.execute` | `dict` with `person_id`, `moderacion`, `fotos_actualizadas` |
| `EliminarPersona.execute` | `dict` with `person_id`, `eliminada`, `fotos` |
| `RegistrarFalla.execute` | `dict` shaped like `ReporteCreado` (`id`, `tipo`, `estado`, `created_at`) |
| `RegistrarPublicacion.execute` | `dict` shaped like `ReporteCreado` |
| `ListarReportesAdmin.execute` | `list[ReporteAdmin]` |
| `CambiarEstadoReporte.execute` | `dict` with `id`, `estado` |

#### Scenario: RegistrarBusqueda.execute returns ResultadoBusqueda

- GIVEN valid processed photos and form data
- WHEN `RegistrarBusqueda.execute(...)` is called
- THEN it returns a `ResultadoBusqueda` Pydantic model with `codigo`, `total`, and `coincidencias` fields populated

#### Scenario: RegistrarFalla.execute returns ReporteCreado-shaped dict

- GIVEN a `ReporteFallaIn` payload
- WHEN `RegistrarFalla.execute(...)` is called
- THEN it returns a dict with `id`, `tipo='falla'`, `estado='pendiente'`, and `created_at`

#### Scenario: ListarReportesAdmin.execute returns list[ReporteAdmin]

- GIVEN a `ReporteRepository` with seeded reports
- WHEN `ListarReportesAdmin.execute(tipo=None, estado=None, limite=100)` is called
- THEN it returns a list of `ReporteAdmin` Pydantic models ordered by most recent first

### Domain Exceptions

#### Requirement: Shared domain exceptions module

The system MUST define a domain exception module at `app/shared/_exceptions.py` with the following exceptions, used by every bounded context:

- `PersonaValidationError` — raised when form data is invalid (missing required fields, no face detected, business rule violations)
- `RostroNoDetectadoError` — raised when no face is detected in an uploaded photo (may be a subclass of `PersonaValidationError` or a distinct exception)
- `PersonaNotFoundError` — raised when a `person_id`, `reporte_id`, or other expected record does not exist
- `ModificacionInvalidaError` — raised when an invalid moderation or status value is provided

Use cases MUST raise these domain exceptions. Use cases MUST NOT raise `HTTPException` or any HTTP-framework-specific exception.

#### Requirement: Endpoints map domain exceptions to HTTP status codes

Each endpoint that calls a use case MUST catch domain exceptions and map them to HTTP status codes:

- `PersonaValidationError` → `HTTPException(status_code=422)`
- `RostroNoDetectadoError` → `HTTPException(status_code=422)`
- `PersonaNotFoundError` → `HTTPException(status_code=404)`
- `ModificacionInvalidaError` → `HTTPException(status_code=400)`

#### Scenario: Validation error maps to 422

- GIVEN a request to `POST /buscados` with no `nombre` and no `doc_numero`
- WHEN the request is processed
- THEN `RegistrarBusqueda.execute(...)` raises `PersonaValidationError`
- AND the endpoint catches it and raises `HTTPException(status_code=422, detail=<message>)`

#### Scenario: Reporte publicacion with missing person_id maps to 404

- GIVEN a request to `POST /reportes/publicacion` with a valid UUID that does not match any persona
- WHEN the request is processed
- THEN `RegistrarPublicacion.execute(...)` raises `PersonaNotFoundError`
- AND the endpoint catches it and raises `HTTPException(status_code=404, detail=<message>)`

#### Scenario: Reporte publicacion with invalid person_id maps to 422

- GIVEN a request to `POST /reportes/publicacion` with a `person_id` that is not a UUID
- WHEN the request is processed
- THEN `RegistrarPublicacion.execute(...)` raises `PersonaValidationError`
- AND the endpoint catches it and raises `HTTPException(status_code=422, detail=<message>)`

#### Scenario: Invalid reporte estado maps to 400

- GIVEN a request to `PATCH /admin/reportes/{id}/estado` with `valor="otro"`
- WHEN the request is processed
- THEN `CambiarEstadoReporte.execute(...)` raises `ModificacionInvalidaError`
- AND the endpoint catches it and raises `HTTPException(status_code=400, detail=<message>)`

### PersonaBase Flow

#### Requirement: PersonaRepository.add accepts a PersonaBase

`PersonaRepository.add` MUST accept a `PersonaBase` (Pydantic model from `app/domain/persona.py`) as its primary data argument instead of a `dict[str, Any]`.

The repository MUST internally map `PersonaBase` fields to SQL parameter names (e.g., `persona.es_menor` → `%(menor)s`, `persona.telefono_contacto` → `%(tel_contacto)s`).

#### Scenario: Repository accepts a domain object

- GIVEN a use case that has constructed a `PersonaBase` from form data
- WHEN `repo.add(person_id, persona, procesadas)` is called
- THEN the row is inserted into `personas` with values mapped from `persona` fields
- AND N rows are inserted into `persona_embeddings` (one per processed photo × N embeddings)

#### Scenario: Use case builds PersonaBase from form fields (FAMILIAR)

- GIVEN form data with `nombre`, `apellido`, `edad`, `doc_tipo`, `doc_numero`, `telefono_contacto`
- WHEN `RegistrarBusqueda.execute(...)` is called
- THEN a `PersonaBase` is constructed with:
  - `estado = Estado.BUSCADA`
  - `es_menor = False`
  - `moderacion = "aprobada"`
  - All provided form fields mapped to corresponding `PersonaBase` fields
- AND the `PersonaBase` is passed to `repo.add`

#### Scenario: Use case builds PersonaBase from form fields (RESCATISTA)

- GIVEN form data with `es_menor`, `nombre`, `apellido`, `refugio`, `telefono_responsable`, `doc_responsable`, `descripcion`, `ubicacion`
- WHEN `RegistrarEncontrado.execute(...)` is called
- THEN a `PersonaBase` is constructed with:
  - `estado = Estado.ENCONTRADA`
  - `es_menor` set from form input
  - `moderacion = "pendiente"` (found persons start pending moderation)
  - All provided form fields mapped to corresponding `PersonaBase` fields
- AND the `PersonaBase` is passed to `repo.add`

### Cross-flow Alert

#### Requirement: AlertaFamiliar construction stays inside RegistrarEncontrado

`RegistrarEncontrado.execute(...)` MUST construct the `AlertaFamiliar` (when a cross-flow match exists) internally. The alert construction logic MUST NOT be extracted to a separate use case or service in this change.

When the found person's best embedding match against `buscada` persons has a distance below `MatchingPolicy.threshold`, the result MUST include an `AlertaFamiliar` with the matched person's details.

#### Scenario: Alert is created when a familiar match exists

- GIVEN a found person whose best embedding match against `buscada` persons has distance < threshold
- WHEN `RegistrarEncontrado.execute(...)` is called
- THEN the returned `ResultadoRegistro` includes an `AlertaFamiliar` populated with the matched person's details
- AND `MenoresPrivacy` is applied to the alert (masking `familiar_nombre` if the matched person is a minor)

#### Scenario: No alert when no match exists

- GIVEN a found person whose best embedding match has distance >= threshold
- WHEN `RegistrarEncontrado.execute(...)` is called
- THEN the returned `ResultadoRegistro` has `alerta = None`

### Privacy Application

#### Requirement: MenoresPrivacy is applied inside each use case

Each use case that returns persona data MUST apply `MenoresPrivacy` to all returned objects before returning. The use case is responsible for privacy application; the endpoint MUST NOT call `MenoresPrivacy`.

Use cases that MUST apply `MenoresPrivacy`:

- `RegistrarBusqueda` — applies to each `Candidato` in `coincidencias`
- `RegistrarEncontrado` — applies to the `AlertaFamiliar` in the result (if present)
- `BuscarAdmin` — applies to each `Candidato` in the result list
- `ListarPersonasAdmin` — applies to each `PersonaAdmin` in the result list

#### Scenario: RegistrarBusqueda applies MenoresPrivacy

- GIVEN a search returns 10 candidates, 3 of which are minors (`es_menor=True`)
- WHEN `RegistrarBusqueda.execute(...)` returns
- THEN the 3 minor candidates have `nombre=None` and `apellido=None`
- AND the 7 adult candidates have their real names intact

#### Scenario: RegistrarEncontrado applies MenoresPrivacy to alert

- GIVEN a cross-flow match where the matched `buscada` person is a minor
- WHEN `RegistrarEncontrado.execute(...)` returns
- THEN the `AlertaFamiliar` in the result has `familiar_nombre=None`

### In-Memory Fake Repositories

#### Requirement: Fake repositories for testing

In-memory fake implementations of both repositories MUST exist:

- `FakePersonaRepository` at `tests/personas/repositories/fake.py` MUST implement the same public interface as the real `PersonaRepository`:
  - `add(person_id, persona: PersonaBase, procesadas) -> list[str]`
  - `search_by_estado(embedding, estado, limit) -> list[dict]`
  - `search_admin(embedding, estado, limit) -> list[dict]`
  - `list_admin(limit, estado, moderacion) -> list[dict]`
  - `set_moderacion(person_id, valor) -> int`
  - `delete(person_id) -> int`
- `FakeReporteRepository` at `tests/reportes/repositories/fake.py` MUST implement the same public interface as the real `ReporteRepository`:
  - `add_falla(descripcion, url, contacto) -> dict`
  - `add_publicacion(descripcion, person_id, contacto) -> dict`
  - `persona_exists(person_id) -> bool`
  - `list_admin(tipo, estado, limite) -> list[dict]`
  - `set_estado(reporte_id, estado) -> int`

The fakes MUST be test-only and MUST NOT be imported by application code.

#### Scenario: Fake persona repository supports use case tests

- GIVEN a use case test that instantiates a `FakePersonaRepository`
- WHEN `fake.add(...)` is called followed by `fake.search_by_estado(...)`
- THEN the search returns the previously added person data in the expected dict shape
- AND `MatchingPolicy` is used to compute match decisions

#### Scenario: Fake reporte repository supports use case tests

- GIVEN a use case test that instantiates a `FakeReporteRepository` with one registered persona
- WHEN `RegistrarPublicacion.execute(...)` is called with that persona's UUID
- THEN the fake stores the report and `persona_exists` returns `True`

### Test Coverage

#### Requirement: Use case test coverage ≥80% per bounded context

`pytest` MUST pass with ≥80% line coverage on each of the following:

- `app/personas/use_cases/`
- `app/reportes/use_cases/`
- `app/shared/`

#### Scenario: Coverage report passes

- GIVEN all use case tests pass
- WHEN `pytest --cov=app/personas/use_cases --cov=app/reportes/use_cases --cov=app/shared --cov-report=term-missing` is run
- THEN the reported line coverage on each of those packages is ≥80% (current: 100%).

#### Requirement: Domain exceptions are unit-tested

Each domain exception (`PersonaValidationError`, `RostroNoDetectadoError`, `PersonaNotFoundError`, `ModificacionInvalidaError`) MUST be triggered by at least one use case unit test in at least one bounded context that verifies:

- The exception type is raised
- The exception carries an appropriate error message

#### Scenario: PersonaValidationError triggered in RegistrarBusqueda

- GIVEN a use case test for `RegistrarBusqueda` with no `nombre` and no `doc_numero`
- WHEN `RegistrarBusqueda.execute(...)` is called
- THEN it raises `PersonaValidationError`

#### Scenario: PersonaNotFoundError triggered in EliminarPersona

- GIVEN a use case test for `EliminarPersona` with a `person_id` not in the fake repository
- WHEN `EliminarPersona.execute(...)` is called
- THEN it raises `PersonaNotFoundError`

#### Scenario: PersonaNotFoundError triggered in RegistrarPublicacion

- GIVEN a use case test for `RegistrarPublicacion` with a `person_id` UUID that has not been registered
- WHEN `RegistrarPublicacion.execute(...)` is called
- THEN it raises `PersonaNotFoundError`

#### Scenario: ModificacionInvalidaError triggered in CambiarEstadoReporte

- GIVEN a use case test for `CambiarEstadoReporte` with `valor="otro"`
- WHEN `CambiarEstadoReporte.execute(...)` is called
- THEN it raises `ModificacionInvalidaError`

### Backward Compatibility

#### Requirement: API contract preserved

The HTTP API contract (endpoint routes, request shapes, response shapes, status codes) MUST be preserved after this change. API clients MUST NOT need to change their integration code.

#### Scenario: Same response shape for POST /buscados

- GIVEN a valid `POST /buscados` request made before and after this change
- WHEN both requests are processed
- THEN both responses have the same `ResultadoBusqueda` shape (`codigo`, `total`, `coincidencias`)

#### Scenario: Same response shape for POST /encontrados

- GIVEN a valid `POST /encontrados` request made before and after this change
- WHEN both requests are processed
- THEN both responses have the same `ResultadoRegistro` shape (`codigo`, `person_id`, `alerta`)

#### Scenario: Same response shape for admin endpoints

- GIVEN valid admin requests to `GET /admin/personas`, `PATCH /admin/personas/{id}/moderacion`, and `DELETE /admin/personas/{id}` made before and after this change
- WHEN the requests are processed
- THEN the response bodies and status codes are identical

#### Scenario: Same response shape for report endpoints

- GIVEN valid requests to `POST /reportes/falla`, `POST /reportes/publicacion`, `GET /admin/reportes`, and `PATCH /admin/reportes/{id}/estado` made before and after this change
- WHEN the requests are processed
- THEN the response bodies and status codes are identical
- AND in particular, `POST /reportes/publicacion` with a missing `person_id` returns HTTP 404 (not 422) and a malformed `person_id` returns HTTP 422

### Existing Tests

#### Requirement: Existing domain tests continue to pass

All existing tests in `tests/domain/` (21 tests covering `MatchingPolicy` and `MenoresPrivacy`) MUST continue to pass after this change.

#### Scenario: Domain tests pass

- GIVEN this change is applied
- WHEN `pytest tests/domain/` is run
- THEN all 21 tests pass with 100% coverage on `app/domain/`
