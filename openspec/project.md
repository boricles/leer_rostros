# Reencuentros — Project Context

## Purpose

Facial-recognition service for reuniting missing persons with their families after a humanitarian crisis (Venezuela earthquake). A family member uploads a photo of the person they're looking for; a rescuer uploads a photo of someone they found; the system performs facial matching and alerts when a match is found.

## Stack

| Component | Technology | Role |
|-----------|-----------|------|
| **API** | FastAPI + uvicorn (pm2-managed) | REST endpoints, Swagger at `/api/docs` |
| **Face engine** | DeepFace (Facenet512 + retinaface) | 512-dim embedding extraction |
| **Vector DB** | PostgreSQL 16 + pgvector (HNSW index, cosine) | Vector storage and similarity search |
| **Image storage** | DigitalOcean Spaces (S3-compatible, boto3) | Original image persistence |
| **Configuration** | pydantic-settings (.env) | Environment-based config |
| **Schemas** | pydantic v2 | Request/response validation |
| **Frontend** | Single-file HTML+CSS+JS | 3 tabs: familiar / rescatista / admin |

## Infrastructure

- **Droplet**: DigitalOcean (137.184.107.94), Ubuntu 24.04
- **Domain**: symtechven.com (nginx reverse proxy, SSL via Certbot)
- **Docker**: docker-compose (api + pgvector/pgvector:pg16)
- **Volumes**: 20 GB volume for code, venv, DeepFace weights, and Postgres data
- **Process manager**: pm2 (service name: `rostros-api`)

## Repository Layout (key files)

```
app/
  main.py        # FastAPI endpoints, 4 routes
  config.py      # pydantic-settings Settings class
  database.py    # psycopg pool, init_db, pgvector extension, HNSW index
  faces.py       # DeepFace embedding extraction + warmup
  storage.py     # boto3 upload/delete to DigitalOcean Spaces
  schemas.py     # Pydantic response models
frontend/
  index.html     # Single-file SPA
evaluate.py      # Model benchmark (5 models × 3 detectors)
benchmark_lfw.py # LFW benchmark
benchmark_dlib.py# dlib/face-api.js comparison
Dockerfile       # python:3.11-slim
docker-compose.yml
requirements.txt
ARQUITECTURA.md  # Architectural docs (Spanish)
CLAUDE.md        # V0 prototype reference (ChromaDB era)
AGENTS.md        # Alias for CLAUDE.md
```

## Endpoints

| Method | Route | Tags | Description |
|--------|-------|------|-------------|
| `GET` | `/health` | sistema | Service health check |
| `POST` | `/buscados` | familiar | Register missing person search, return matches |
| `POST` | `/encontrados` | rescatista | Register found person, alert if family searched |
| `POST` | `/buscar` | admin | Compare photo against entire database |
| `GET` | `/admin/personas` | admin | List all records |

## Domain Model

- **personas** table (one row per photo, multiple photos share `person_id`):
  - `id` (UUID PK), `person_id` (UUID, groups photos), `estado` ('buscada'|'encontrada')
  - `es_menor` (bool — triggers privacy protocol)
  - `nombre`, `apellido`, `edad`, `doc_tipo`, `doc_numero`
  - `telefono_contacto`, `refugio`, `telefono_responsable`, `doc_responsable`
  - `descripcion`, `ubicacion`, `codigo` (e.g., "REE-XXXXXXXX")
  - `image_url`, `image_key`, `embedding` (vector), `created_at`

## Design Decisions

1. **Model choice**: Facenet512 + retinaface — selected after evaluating 5 models × 3 detectors on real labeled photos. SFace was initially chosen but Facenet512 generalizes better to varied rescue photos.
2. **Match threshold**: 0.50 (cosine distance). Calibrated with real data: same-person ≤0.469, different-people ≥0.549.
3. **HNSW index** (not ivfflat): ivfflat skips rows with small datasets, HNSW works correctly at any scale.
4. **Import order**: `app.database` (psycopg) must be imported before `app.faces` (TensorFlow) to avoid `free(): invalid pointer` crash.
5. **Privacy protocol**: Minors' names are hidden from search results (`nombre=None`, `apellido=None` when `es_menor=True`).
6. **v0 prototype**: Legacy ChromaDB-based code (`load_image.py`, `search_image.py`, `main.py`) slated for deletion.

## Testing

- **Current state**: Zero tests. No pytest config, no test files.
- **Runner**: pytest (de facto standard for Python + FastAPI)
- **Discipline**: Tests alongside code (not strict TDD)

## Active Change: core-domain

See `openspec/changes/core-domain/` for change-specific artifacts.

Scope:

- Persona domain object (Candidate 5)
- MatchingPolicy module (Candidate 3)
- Menores privacy protocol (Candidate 6)
- Delete v0 prototype dead code
