# Design: `core-domain` — Persona Domain, Matching Policy, and Menores Privacy

## 1. Module map

```
app/
  domain/
    __init__.py          # New — re-exports MatchingPolicy, MenoresPrivacy, PersonaBase, Estado, Foto
    matching.py          # New — MatchingPolicy: thresholds, bands, percentage (delegates to faces.distance_to_confidence)
    privacy.py           # New — MenoresPrivacy: callable that masks nombre/apellido/familiar_nombre for minors
    persona.py           # New — Persona entity, Foto dataclass, Estado enum
  repositories/
    __init__.py          # New — re-exports PersonaRepository
    persona.py           # New — PersonaRepository: all SQL for personas + persona_embeddings tables
  main.py                # Heavy refactor — remove inline SQL, _insertar_fotos, _buscar_mejor_por_persona,
                         # _buscar_por_estado, _fila_a_candidato, etc.; add repo + policy wiring;
                         # fix AlertaFamiliar privacy bug; fix data preservation
  config.py              # UNCHANGED — match_threshold=0.55, sigmoid params already correct
  schemas.py             # Minor: add es_menor: bool = False to AlertaFamiliar
  database.py            # UNCHANGED — team's schema (persona_embeddings, moderacion, advisory lock)
  faces.py               # UNCHANGED — team's InsightFace buffalo_l implementation
  storage.py             # UNCHANGED — local fallback + Spaces

frontend/
  index.html             # Minor: remove redundant c.es_menor nulling; auth UI is team's work

tests/
  conftest.py            # New — pytest fixture for FastAPI TestClient, Bearer token fixture
  domain/
    test_matching.py     # New — unit tests for MatchingPolicy
    test_privacy.py      # New — unit tests for MenoresPrivacy
    test_persona.py      # New (optional) — Persona validation, photos aggregation
  repositories/
    test_persona_repo.py # New (optional) — fake repo tests for multi-embeddings, moderation
```

### Purpose summary

| File | Purpose |
|------|---------|
| `app/domain/__init__.py` | Barrel module: re-exports public types so call sites do `from app.domain import MatchingPolicy, MenoresPrivacy, PersonaBase` |
| `app/domain/matching.py` | `MatchingPolicy` dataclass loaded from `Settings.match_threshold`; owns `is_match`, `confidence_band`, `match_percentage` (delegates to `faces.distance_to_confidence`) |
| `app/domain/privacy.py` | `MenoresPrivacy` function: takes a `Candidato`, `PersonaAdmin`, or `AlertaFamiliar` and returns a masked copy when `es_menor=True` |
| `app/domain/persona.py` | `Estado` enum (`BUSCADA`, `ENCONTRADA`), `Foto` dataclass (image_url, image_key), `PersonaBase` Pydantic model |
| `app/repositories/__init__.py` | Barrel module: re-exports `PersonaRepository` |
| `app/repositories/persona.py` | `PersonaRepository` class owning ALL SQL for `personas` and `persona_embeddings`: multi-embedding INSERT, `ROW_NUMBER() OVER (PARTITION BY ...)` search, moderation filter, admin search, `set_moderacion`, `delete` |
| `tests/conftest.py` | Pytest config: sys.path fix, `client` fixture wrapping `TestClient(app)`, Bearer token fixture (`sha256("reencuentros::" + admin_password)`) |
| `tests/domain/test_matching.py` | Unit tests: `is_match` boundary cases, `confidence_band` all three bands, `match_percentage` sigmoid behavior |
| `tests/domain/test_privacy.py` | Unit tests: masking minors, passthrough adults, original-immutable copy, `AlertaFamiliar.familiar_nombre` masking |
| `tests/domain/test_persona.py` | (Optional) Unit tests: `PersonaBase` validation, `Estado` enum, photos |
| `tests/repositories/test_persona_repo.py` | (Optional) In-memory fake tests for repository multi-embedding and moderation logic |

---

## 2. Public interfaces

### `app/domain/matching.py`

```python
# app/domain/matching.py

from dataclasses import dataclass
from typing import Literal

from app import faces

Confianza = Literal["alta", "media", "baja"]


@dataclass(frozen=True)
class MatchingPolicy:
    """Single source of truth for match decisions.

    Loaded from Settings.match_threshold at app startup.
    Confidence bands are class defaults calibrated for InsightFace buffalo_l.
    match_percentage delegates to faces.distance_to_confidence (sigmoid).
    """
    threshold: float
    conf_alta: float = 0.40
    conf_media: float = 0.55

    def is_match(self, distance: float) -> bool:
        """True iff distance < self.threshold."""
        return distance < self.threshold

    def confidence_band(self, distance: float) -> Confianza:
        """Return 'alta', 'media', or 'baja' based on configured bands."""
        if distance < self.conf_alta:
            return "alta"
        if distance < self.conf_media:
            return "media"
        return "baja"

    def match_percentage(self, distance: float) -> int:
        """0-100 percentage via sigmoid in faces.distance_to_confidence.

        Replaces the old 1.2 divisor (calibrated for Facenet512 + retinaface,
        no longer applicable). The sigmoid is calibrated for InsightFace buffalo_l
        with k=12.0 and midpoint=0.40.
        """
        return faces.distance_to_confidence(distance)
```

**Key changes from previous design**:

- `conf_media` changed from `0.50` to `0.55` (InsightFace calibration).
- `match_percentage` delegates to `faces.distance_to_confidence(distance)` (sigmoid), not the `1.2` divisor formula.
- Returns `int` (the sigmoid returns a float rounded to 1 decimal; `int()` truncates).

### `app/domain/privacy.py`

```python
# app/domain/privacy.py

from typing import TypeVar

from app.schemas import Candidato, PersonaAdmin, AlertaFamiliar

T = TypeVar("T", Candidato, PersonaAdmin, AlertaFamiliar)


def MenoresPrivacy(obj: T) -> T:
    """Mask nombre/apellido/familiar_nombre when es_menor is True.

    Applied at the API response boundary for ALL regular endpoints —
    public (/buscados, /encontrados) AND admin (/buscar, /admin/personas).

    Args:
        obj: A Candidato, PersonaAdmin, or AlertaFamiliar instance.

    Returns:
        A new instance (copy) with nombre=None and apellido=None when
        obj.es_menor is True. For AlertaFamiliar, familiar_nombre is
        nulled instead. The original object is not mutated.
    """
    if not getattr(obj, "es_menor", False):
        return obj
    if isinstance(obj, AlertaFamiliar):
        return obj.model_copy(update={"familiar_nombre": None})
    return obj.model_copy(update={"nombre": None, "apellido": None})
```

**Key change from previous design**: Applied to ALL regular endpoints (public AND admin per Q1 revised). The "future special super-admin endpoint with role" is out of scope.

### `app/domain/persona.py`

```python
# app/domain/persona.py

from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class Estado(str, Enum):
    """Valid estados for a persona."""
    BUSCADA = "buscada"
    ENCONTRADA = "encontrada"


class Foto:
    """A single photo belonging to a persona."""
    image_url: str
    image_key: str


class PersonaBase(BaseModel):
    """Internal domain model for one logical person with N photos.

    NOT a response model — used by the repository as an internal
    representation before converting to Candidato/PersonaAdmin.
    """
    person_id: UUID
    estado: Estado
    es_menor: bool
    nombre: str | None = None
    apellido: str | None = None
    edad: str | None = None
    doc_tipo: str | None = None
    doc_numero: str | None = None
    telefono_contacto: str | None = None
    refugio: str | None = None
    telefono_responsable: str | None = None
    doc_responsable: str | None = None
    descripcion: str | None = None
    ubicacion: str | None = None
    codigo: str | None = None
    photos: list[str] = []  # list of image_urls
    distancia: float | None = None  # only populated for search results
    moderacion: str = "aprobada"
```

### `app/repositories/persona.py`

```python
# app/repositories/persona.py

from typing import Any
from uuid import UUID

import psycopg
from psycopg_pool import ConnectionPool

from app.domain.matching import MatchingPolicy
from app import storage


class PersonaRepository:
    """All SQL for the personas and persona_embeddings tables.
    No raw SQL for these tables remains in app/main.py.
    """

    # INSERT into personas (one row per photo)
    _INSERT_PERSONA = """
        INSERT INTO personas
          (id, person_id, estado, es_menor, nombre, apellido, edad, doc_tipo,
           doc_numero, telefono_contacto, refugio, telefono_responsable,
           doc_responsable, descripcion, ubicacion, codigo, image_url, image_key)
        VALUES (%(id)s, %(pid)s, %(estado)s, %(menor)s, %(nombre)s, %(apellido)s, %(edad)s,
                %(doc_tipo)s, %(doc_numero)s, %(tel_contacto)s, %(refugio)s, %(tel_resp)s,
                %(doc_resp)s, %(descripcion)s, %(ubicacion)s, %(codigo)s, %(url)s, %(key)s)
    """

    # INSERT into persona_embeddings (one row per embedding)
    _INSERT_EMBEDDING = """
        INSERT INTO persona_embeddings (foto_id, embedding, calidad_rostro)
        VALUES (%s, %s, %s)
    """

    # Search: best match per person via ROW_NUMBER() OVER (PARTITION BY ...)
    # Public: filters by moderacion='aprobada' and optionally estado
    _SEARCH = """
        SELECT {cols}, b.distancia
        FROM (
            SELECT pe.foto_id, p.person_id,
                   pe.embedding <=> %s AS distancia,
                   ROW_NUMBER() OVER (
                       PARTITION BY p.person_id ORDER BY pe.embedding <=> %s ASC
                   ) AS rn
            FROM persona_embeddings pe
            JOIN personas p ON p.id = pe.foto_id
            WHERE p.moderacion = 'aprobada'
                {estado_filter}
        ) b
        JOIN personas p2 ON p2.id = b.foto_id
        WHERE b.rn = 1
        ORDER BY b.distancia ASC
        LIMIT %s
    """

    # Admin search: same ROW_NUMBER() but NO moderacion filter
    _SEARCH_ADMIN = """
        SELECT {cols}, b.distancia
        FROM (
            SELECT pe.foto_id, p.person_id,
                   pe.embedding <=> %s AS distancia,
                   ROW_NUMBER() OVER (
                       PARTITION BY p.person_id ORDER BY pe.embedding <=> %s ASC
                   ) AS rn
            FROM persona_embeddings pe
            JOIN personas p ON p.id = pe.foto_id
                {estado_filter}
        ) b
        JOIN personas p2 ON p2.id = b.foto_id
        WHERE b.rn = 1
        ORDER BY b.distancia ASC
        LIMIT %s
    """

    # Admin list: aggregation with moderation column
    _LIST_ADMIN = """
        SELECT person_id, max(estado), bool_or(es_menor), max(nombre), max(apellido),
               max(edad), max(doc_numero), max(refugio), max(ubicacion),
               coalesce(max(telefono_responsable), max(telefono_contacto)),
               max(codigo), max(moderacion), array_agg(image_url), min(created_at)
        FROM personas {where}
        GROUP BY person_id ORDER BY min(created_at) DESC LIMIT %s
    """

    # Update moderation status
    _SET_MODERACION = """
        UPDATE personas SET moderacion = %s WHERE person_id = %s
    """

    # Delete persona and (via ON DELETE CASCADE) embeddings
    _DELETE = """
        DELETE FROM personas WHERE person_id = %s
    """

    _SELECT_IMAGE_KEYS = """
        SELECT image_key FROM personas WHERE person_id = %s
    """

    def __init__(self, pool: ConnectionPool, policy: MatchingPolicy):
        self._pool = pool
        self._policy = policy

    def add(
        self,
        person_id: UUID,
        datos: dict[str, Any],
        procesadas: list[tuple[bytes, str, list[tuple[Any, float]]]],
    ) -> list[str]:
        """Insert one row per photo into personas + N embeddings per photo into persona_embeddings.

        Args:
            person_id: UUID grouping all photos.
            datos: dict with estado, menor, nombre, apellido, etc.
            procesadas: list of (image_data, content_type, [(embedding, calidad), ...]).

        Returns:
            List of uploaded image URLs.
        """
        urls = []
        with self._pool.connection() as conn:
            for data, ct, embs in procesadas:
                ext = CONTENT_EXT.get(ct, "jpg")
                foto_id = uuid.uuid4()
                key = f"personas/{foto_id}.{ext}"
                url = storage.upload_image(data, key, ct)
                conn.execute(self._INSERT_PERSONA, {
                    **datos, "id": foto_id, "pid": person_id, "url": url, "key": key,
                })
                for emb, calidad in embs:
                    conn.execute(self._INSERT_EMBEDDING, (foto_id, emb, calidad))
                conn.commit()
                urls.append(url)
        return urls

    def search_by_estado(
        self, embedding, estado: str | None, limit: int,
    ) -> list[dict]:
        """Search personas by embedding, filtered by moderacion='aprobada'.

        Uses ROW_NUMBER() OVER (PARTITION BY p.person_id ORDER BY pe.embedding <=> %s ASC)
        to get the best match per person across all embeddings.

        Returns list of Candidato-shaped dicts with distancia, coincidencia, confianza.
        Does NOT apply privacy masking (call MenoresPrivacy at the endpoint level).
        """
        cols = _cols_with_alias("p2")
        estado_filter = "AND p.estado = %s" if estado else ""
        params: tuple = (embedding, embedding)
        if estado:
            params = params + (estado,)
        params = params + (limit,)
        sql = self._SEARCH.format(cols=cols, estado_filter=estado_filter)
        with self._pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_candidato_dict(r) for r in rows]

    def search_admin(
        self, embedding, estado: str | None, limit: int,
    ) -> list[dict]:
        """Admin search: same as search_by_estado but NO moderacion filter.

        Returns list of Candidato-shaped dicts. Does NOT apply privacy masking.
        """
        cols = _cols_with_alias("p2")
        estado_filter = "WHERE p.estado = %s" if estado else ""
        params: tuple = (embedding, embedding)
        if estado:
            params = params + (estado,)
        params = params + (limit,)
        sql = self._SEARCH_ADMIN.format(cols=cols, estado_filter=estado_filter)
        with self._pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_candidato_dict(r) for r in rows]

    def list_admin(
        self, limit: int, estado: str | None = None, moderacion: str | None = None,
    ) -> list[dict]:
        """List personas for admin view, with optional estado/moderacion filters.

        Returns list of PersonaAdmin-shaped dicts. Does NOT apply privacy masking.
        """
        conds, args = [], []
        if estado in ("buscada", "encontrada"):
            conds.append("estado = %s")
            args.append(estado)
        if moderacion in ("aprobada", "rechazada", "pendiente"):
            conds.append("moderacion = %s")
            args.append(moderacion)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        args.append(limit)
        sql = self._LIST_ADMIN.format(where=where)
        with self._pool.connection() as conn:
            rows = conn.execute(sql, tuple(args)).fetchall()
        return [self._row_to_admin_dict(r) for r in rows]

    def set_moderacion(self, person_id: str, valor: str) -> int:
        """Update moderacion for all rows with the given person_id.

        Returns number of rows updated.
        """
        with self._pool.connection() as conn:
            n = conn.execute(self._SET_MODERACION, (valor, person_id)).rowcount
            conn.commit()
        return n

    def delete(self, person_id: str) -> int:
        """Delete persona (and embeddings via ON DELETE CASCADE).

        Also removes images from storage. Returns number of photos deleted.
        """
        with self._pool.connection() as conn:
            rows = conn.execute(self._SELECT_IMAGE_KEYS, (person_id,)).fetchall()
            if not rows:
                return 0
            keys = [r[0] for r in rows]
            conn.execute(self._DELETE, (person_id,))
            conn.commit()
        for key in keys:
            try:
                storage.delete_image(key)
            except Exception:
                pass  # best-effort cleanup
        return len(keys)

    def _row_to_candidato_dict(self, row: tuple) -> dict:
        """Convert one SQL row from search queries into a Candidato-shaped dict."""
        (person_id, estado, es_menor, nombre, apellido, edad, refugio, ubicacion,
         tel_resp, tel_contacto, descripcion, image_url, distancia) = row
        d = float(distancia)
        return {
            "person_id": str(person_id),
            "estado": estado,
            "es_menor": bool(es_menor),
            "nombre": nombre,
            "apellido": apellido,
            "edad": edad,
            "refugio": refugio,
            "ubicacion": ubicacion or refugio,
            "telefono": tel_resp or tel_contacto,
            "descripcion": descripcion,
            "image_url": image_url,
            "distancia": round(d, 4),
            "coincidencia": self._policy.match_percentage(d),
            "confianza": self._policy.confidence_band(d),
        }

    def _row_to_admin_dict(self, row: tuple) -> dict:
        """Convert one admin aggregation row into a PersonaAdmin-shaped dict."""
        (person_id, estado, es_menor, nombre, apellido, edad, doc, refugio, ubicacion,
         telefono, codigo, moderacion, fotos, created_at) = row
        return {
            "person_id": str(person_id),
            "estado": estado,
            "es_menor": bool(es_menor),
            "nombre": nombre,
            "apellido": apellido,
            "edad": edad,
            "doc": doc,
            "refugio": refugio,
            "ubicacion": ubicacion,
            "telefono": telefono,
            "codigo": codigo,
            "moderacion": moderacion,
            "fotos": list(fotos),
            "created_at": created_at,
        }
```

**Key changes from previous design**:

- **MAJOR**: Repository now handles TWO tables (`personas` and `persona_embeddings`).
- `add` takes `procesadas: list[tuple[data, content_type, list[tuple[embedding, calidad]]]]` (multi-embeddings per photo).
- `search_by_estado` uses `ROW_NUMBER() OVER (PARTITION BY p.person_id ORDER BY pe.embedding <=> %s ASC)` and filters by `moderacion='aprobada'`.
- New `search_admin` method: same query but NO moderation filter.
- New `set_moderacion` method: `UPDATE personas SET moderacion = %s WHERE person_id = %s`.
- New `delete` method: deletes personas (embeddings cascade) + cleans up storage.
- `list_admin` now supports optional `moderacion` filter.

---

## 3. Data flow

### 3.1 `POST /buscados` (familiar registration)

```
Client → POST /buscados
  │
  ├─ files → _procesar_fotos(files) → procesadas: [(data, ct, [(emb, qual), ...])]
  │
  ├─ person_id = uuid4(), codigo = gen_codigo()
  │
  ├─ datos = {estado="buscada", menor=False, nombre, apellido, ...}
  │
  ├─ repo.add(person_id, datos, procesadas) → urls
  │
  ├─ embedding = _embedding_consulta(procesadas)  # base embedding of first photo
  │
  ├─ repo.search_by_estado(embedding, estado="encontrada", limit=limite)
  │     → list[dict] with distancia, coincidencia (sigmoid), confianza
  │     (uses ROW_NUMBER() OVER (PARTITION BY ...) + moderacion='aprobada' filter)
  │
  ├─ candidatos = [Candidato(**d) for d in results]
  │
  ├─ candidatos = [MenoresPrivacy(c) for c in candidatos]   ← PRIVACY APPLIED (Q1 revised)
  │
  └─ return ResultadoBusqueda(codigo, total, coincidencias)
```

**Key changes**: Multi-embeddings per photo; moderation filter; privacy applied.

### 3.2 `POST /encontrados` (rescatista registration with cross-flow alert)

```
Client → POST /encontrados
  │
  ├─ files → _procesar_fotos(files) → procesadas
  │
  ├─ person_id = uuid4(), codigo = gen_codigo()
  │
  ├─ datos = {estado="encontrada", menor=es_menor, nombre, apellido, ...}
  │     NOTE: nombre/apellido stored as-is (NOT nulled for minors) ← DATA PRESERVATION FIX
  │
  ├─ repo.add(person_id, datos, procesadas) → urls
  │
  ├─ embedding = _embedding_consulta(procesadas)
  │
  ├─ repo.search_by_estado(embedding, estado="buscada", limit=1)
  │     → list[dict]
  │
  ├─ if results and policy.is_match(results[0].distancia):
  │     best = results[0]
  │     alerta = AlertaFamiliar(
  │         person_id=best["person_id"],
  │         familiar_nombre=best["nombre"],
  │         familiar_telefono=best["telefono"],
  │         image_url=best["image_url"],
  │         coincidencia=best["coincidencia"],
  │         confianza=best["confianza"],
  │         es_menor=best["es_menor"],                    ← new field
  │     )
  │     alerta = MenoresPrivacy(alerta)               ← PRIVACY APPLIED (bug fix)
  │
  └─ return ResultadoRegistro(codigo, person_id, alerta)
```

**Key changes**: Data preservation (store real names for minors); `policy.is_match()` instead of `d < CONF_MEDIA`; `AlertaFamiliar` gets `es_menor` field and `MenoresPrivacy` applied.

### 3.3 `POST /admin/login` (auth)

```
Client → POST /admin/login (no auth required)
  │
  ├─ Body: {"usuario": "admin", "password": "..."}
  │
  ├─ Validate credentials against Settings.admin_user / Settings.admin_password
  │
  ├─ token = sha256("reencuentros::" + admin_password)
  │
  └─ return LoginResp(token=token, tipo="Bearer")
```

**Note**: Auth logic stays in `app/main.py` (`_admin_token()`, `requiere_admin()`). Not moved to repository.

### 3.4 `POST /buscar` (admin search — auth required)

```
Client → POST /buscar (admin, Bearer token required)
  │
  ├─ file → faces.embedding_from_bytes(data) → embedding
  │
  ├─ repo.search_admin(embedding, estado=form_estado, limit=limite)
  │     → list[dict]
  │     (uses ROW_NUMBER() OVER (PARTITION BY ...) — NO moderacion filter)
  │
  ├─ candidatos = [Candidato(**d) for d in results]
  │
  ├─ candidatos = [MenoresPrivacy(c) for c in candidatos]   ← PRIVACY APPLIED (Q1 revised)
  │
  └─ return candidatos
```

**Key change from previous design**: Privacy IS applied (Q1 revised). Admin search masks minor names, same as public endpoints.

### 3.5 `GET /admin/personas` (admin list — auth required)

```
Client → GET /admin/personas (admin, Bearer token required)
  │
  ├─ repo.list_admin(limit, estado=form_estado, moderacion=form_moderacion)
  │     → list[dict]
  │
  ├─ personas = [PersonaAdmin(**d) for d in results]
  │
  ├─ personas = [MenoresPrivacy(p) for p in personas]   ← PRIVACY APPLIED (Q1 revised)
  │
  └─ return personas
```

**Key change from previous design**: Privacy IS applied (Q1 revised). Admin list masks minor names.

### 3.6 `PATCH /admin/personas/{id}/moderacion` (admin)

```
Client → PATCH /admin/personas/{id}/moderacion?valor=aprobada (admin, Bearer token required)
  │
  ├─ Validate valor in ("aprobada", "rechazada", "pendiente")
  │
  ├─ repo.set_moderacion(person_id=id, valor=valor) → rows_updated
  │
  ├─ If rows_updated == 0 → HTTP 404
  │
  └─ return {person_id, moderacion, fotos_actualizadas}
```

### 3.7 `DELETE /admin/personas/{id}` (admin)

```
Client → DELETE /admin/personas/{id} (admin, Bearer token required)
  │
  ├─ repo.delete(person_id=id) → photos_deleted
  │
  ├─ If photos_deleted == 0 → HTTP 404
  │
  └─ return {person_id, eliminada, fotos}
```

**Key design decision**: Image cleanup (`storage.delete_image`) is handled inside `PersonaRepository.delete` (best-effort, try/except per key), not in the endpoint handler. The ON DELETE CASCADE in the schema handles `persona_embeddings` cleanup automatically.

---

## 4. SQL ownership

All SQL strings referencing the `personas` or `persona_embeddings` tables move from `app/main.py` to `app/repositories/persona.py`.

### SQL strings that move

| Old location (main.py) | New location (PersonaRepository) | Purpose |
|------------------------|-----------------------------------|---------|
| `_insertar_fotos` INSERT into `personas` (line ~110) | `_INSERT_PERSONA` | Insert one row per photo |
| `_insertar_fotos` INSERT into `persona_embeddings` (line ~122) | `_INSERT_EMBEDDING` | Insert one row per embedding |
| `_buscar_mejor_por_persona` + `_buscar_por_estado` (ROW_NUMBER query) | `_SEARCH` | Public search with `moderacion='aprobada'` filter |
| `buscar_admin` inline ROW_NUMBER query | `_SEARCH_ADMIN` | Admin search (no moderation filter) |
| `listar` aggregation query (line ~280) | `_LIST_ADMIN` | Admin list with optional estado/moderacion filters |
| `moderar` UPDATE (line ~310) | `_SET_MODERACION` | Update moderation status |
| `eliminar` SELECT image_keys + DELETE (line ~322) | `_SELECT_IMAGE_KEYS` + `_DELETE` | Delete persona + cleanup storage |

### SQL strings that stay in `app/main.py` (not domain-related)

None — all SQL for `personas` and `persona_embeddings` is moved. The only SQL remaining in `main.py` would be for non-domain tables (e.g., `admins` table for auth), which is outside this change's scope.

### New signatures

```python
class PersonaRepository:
    def __init__(self, pool: ConnectionPool, policy: MatchingPolicy): ...

    def add(
        self,
        person_id: UUID,
        datos: dict[str, Any],
        procesadas: list[tuple[bytes, str, list[tuple[Any, float]]]],
    ) -> list[str]:
        """Insert one row per photo + N embeddings per photo. Returns URLs."""

    def search_by_estado(
        self, embedding, estado: str | None, limit: int,
    ) -> list[dict]:
        """Search with moderacion='aprobada' filter. Returns Candidato-shaped dicts."""

    def search_admin(
        self, embedding, estado: str | None, limit: int,
    ) -> list[dict]:
        """Search WITHOUT moderacion filter. Returns Candidato-shaped dicts."""

    def list_admin(
        self, limit: int, estado: str | None = None, moderacion: str | None = None,
    ) -> list[dict]:
        """List personas for admin view. Returns PersonaAdmin-shaped dicts."""

    def set_moderacion(self, person_id: str, valor: str) -> int:
        """Update moderacion for all rows with the given person_id."""

    def delete(self, person_id: str) -> int:
        """Delete persona + embeddings (cascade) + storage cleanup. Returns photo count."""
```

---

## 5. Selective privacy application

The `MenoresPrivacy` function is applied at the **response boundary**, after the repository returns data and before the endpoint constructs its Pydantic response model.

### Q1 revised: Apply to ALL regular endpoints

Per the revised Q1 decision, `MenoresPrivacy` is applied to ALL regular endpoints:

| Endpoint | Privacy applied? | Reason |
|----------|-----------------|--------|
| `POST /buscados` (public) | ✅ Yes | Public-facing; minor names must be masked |
| `POST /encontrados` (public) | ✅ Yes (on `AlertaFamiliar`) | Cross-flow alert must not leak minor names |
| `POST /buscar` (admin) | ✅ Yes (Q1 revised) | Regular admin endpoint; masks minor names |
| `GET /admin/personas` (admin) | ✅ Yes (Q1 revised) | Regular admin endpoint; masks minor names |
| `PATCH /admin/personas/{id}/moderacion` | N/A | Does not return persona data |
| `DELETE /admin/personas/{id}` | N/A | Does not return persona data |
| Future "super-admin with role" endpoint | ❌ No (out of scope) | Deferred to a future change |

### Why inline, not a builder parameter?

**Decision**: Inline application at each call site, NOT a builder with a `apply_privacy: bool` parameter.

**Justification** (unchanged from previous design):

- The number of call sites is small (4 endpoints).
- Inline is more explicit and easier to audit: search for `MenoresPrivacy(` to see exactly where it is and isn't applied.
- Privacy is a response-layer concern, not a data-layer concern.

---

## 6. File changes (concrete diff plan)

| File | Change | Lines (rough) |
|------|--------|---------------|
| **New** `app/domain/__init__.py` | Barrel: re-exports `MatchingPolicy`, `Confianza`, `MenoresPrivacy`, `PersonaBase`, `Estado`, `Foto` | ~10 |
| **New** `app/domain/matching.py` | `MatchingPolicy` dataclass with `is_match`, `confidence_band`, `match_percentage` (delegates to sigmoid) | ~40 |
| **New** `app/domain/privacy.py` | `MenoresPrivacy` function handling `Candidato`, `PersonaAdmin`, `AlertaFamiliar` | ~30 |
| **New** `app/domain/persona.py` | `Estado` enum, `Foto` dataclass, `PersonaBase` Pydantic model | ~50 |
| **New** `app/repositories/__init__.py` | Barrel: re-exports `PersonaRepository` | ~5 |
| **New** `app/repositories/persona.py` | `PersonaRepository` with multi-embedding INSERT, ROW_NUMBER search, moderation filter, admin search, set_moderacion, delete | ~200 |
| `app/main.py` | Remove `_COLS`, `_sel`, `_insertar_fotos`, `_buscar_mejor_por_persona`, `_buscar_por_estado`, `_fila_a_candidato`, `nivel_confianza`, `pct_coincidencia`, `CONF_ALTA`, `CONF_MEDIA`. Add `repo` and `policy` wiring. Fix `registrar_encontrado` to NOT null names. Apply `MenoresPrivacy` to `AlertaFamiliar`. Apply `MenoresPrivacy` to admin endpoints. Wire moderation + delete to repo. | net -120 to -150 (more inline SQL to remove than previous design) |
| `app/schemas.py` | Add `es_menor: bool = False` to `AlertaFamiliar` | +3 |
| `app/faces.py` | **UNCHANGED** — team's InsightFace implementation | 0 |
| `app/database.py` | **UNCHANGED** — team's schema (persona_embeddings, moderacion) | 0 |
| `app/storage.py` | **UNCHANGED** | 0 |
| `app/config.py` | **UNCHANGED** — match_threshold=0.55 already correct | 0 |
| `frontend/index.html` | Remove redundant `c.es_menor` nulling in `candHTML`; auth UI is team's work | net -5 |
| `CLAUDE.md` / `AGENTS.md` | Rewrite: describe pgvector/InsightFace buffalo_l/FastAPI stack | rewrite (~80 lines each) |
| `requirements.txt` | Add `pytest`, `httpx`, `pytest-asyncio` | +5 |
| **New** `tests/conftest.py` | sys.path fix, `client` fixture, `policy` fixture, Bearer token fixture | ~35 |
| **New** `tests/domain/test_matching.py` | ~15 tests: is_match, confidence_band, match_percentage sigmoid behavior | ~80 |
| **New** `tests/domain/test_privacy.py` | ~8 tests: masking minors, passthrough adults, immutability, AlertaFamiliar | ~60 |
| **New** `tests/domain/test_persona.py` | (Optional) ~5 tests: PersonaBase validation, Estado enum, photos | ~40 |
| **New** `tests/repositories/test_persona_repo.py` | (Optional) In-memory fake tests for multi-embeddings, moderation | ~80 |
| **New** `tests/test_auth.py` | Auth tests: Bearer token fixture; admin endpoints require auth (401 without) | ~50 |
| **Deleted** `load_image.py` | v0 ChromaDB prototype | -1.4 KB |
| **Deleted** `search_image.py` | v0 ChromaDB prototype | -1.8 KB |
| **Deleted** `main.py` (repo root) | v0 scratchpad | -390 B |
| **Deleted** `haarcascade_frontalface_default.xml` | Unused OpenCV cascade | -963 KB |

**Total estimated new/modified lines**: ~700-800 (tighter than previous estimate due to more SQL and auth tests, still within the 800-line review budget).

---

## 7. Test strategy

### Layout

```
tests/
  conftest.py
  test_auth.py                 # Auth: Bearer token, admin endpoints require auth
  domain/
    test_matching.py
    test_privacy.py
    test_persona.py            # optional
  repositories/
    test_persona_repo.py       # optional (in-memory fake)
```

### `tests/conftest.py`

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import hashlib
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.domain.matching import MatchingPolicy
from app.config import get_settings


@pytest.fixture
def client():
    """FastAPI TestClient — does NOT start lifespan (no DB/DeepFace)."""
    return TestClient(app)


@pytest.fixture
def policy():
    """Default MatchingPolicy with the production threshold."""
    return MatchingPolicy(threshold=0.55)


@pytest.fixture
def admin_token():
    """Valid Bearer token for admin endpoint tests."""
    s = get_settings()
    token = hashlib.sha256(("reencuentros::" + s.admin_password).encode()).hexdigest()
    return f"Bearer {token}"


@pytest.fixture
def admin_headers(admin_token):
    """Headers dict with valid Bearer token."""
    return {"Authorization": admin_token}
```

### `tests/test_auth.py`

| Test | What it covers |
|------|---------------|
| `test_admin_login_returns_token` | `POST /admin/login` with valid credentials returns `LoginResp` with token |
| `test_admin_login_invalid_password` | `POST /admin/login` with wrong password returns 401 |
| `test_admin_endpoint_requires_auth_buscar` | `POST /buscar` without token returns 401 |
| `test_admin_endpoint_requires_auth_listar` | `GET /admin/personas` without token returns 401 |
| `test_admin_endpoint_requires_auth_moderar` | `PATCH /admin/personas/{id}/moderacion` without token returns 401 |
| `test_admin_endpoint_requires_auth_eliminar` | `DELETE /admin/personas/{id}` without token returns 401 |
| `test_admin_endpoint_with_valid_token` | `GET /admin/personas` with valid Bearer token returns 200 |

**Note**: These tests mock or skip anything requiring DB/DeepFace boot. They validate auth gate behavior only.

### `tests/domain/test_matching.py` — ≥80% line coverage

| Test | What it covers |
|------|---------------|
| `test_is_match_below_threshold` | `is_match(0.45)` → True with threshold=0.55 |
| `test_is_match_at_threshold` | `is_match(0.55)` → False (strict `<`) |
| `test_is_match_above_threshold` | `is_match(0.60)` → False |
| `test_is_match_zero_distance` | `is_match(0.0)` → True |
| `test_confidence_band_alta` | `confidence_band(0.30)` → "alta" |
| `test_confidence_band_media` | `confidence_band(0.45)` → "media" |
| `test_confidence_band_baja` | `confidence_band(0.60)` → "baja" |
| `test_confidence_band_at_alta_boundary` | `confidence_band(0.40)` → "media" (strict `<`) |
| `test_confidence_band_at_media_boundary` | `confidence_band(0.55)` → "baja" |
| `test_match_percentage_delegates_to_sigmoid` | `match_percentage(0.36)` → ~62 (sigmoid, not 1.2 divisor) |
| `test_match_percentage_zero` | `match_percentage(0.0)` → 100 |
| `test_match_percentage_at_threshold` | `match_percentage(0.55)` → ~16 |
| `test_custom_threshold` | `MatchingPolicy(threshold=0.30).is_match(0.25)` → True |
| `test_confidence_band_with_custom_bands` | Custom conf_alta/conf_media values work |

**Key change from previous design**: `match_percentage` now delegates to `faces.distance_to_confidence` (sigmoid), so tests verify sigmoid behavior instead of the `1.2` divisor formula. Tests may need to mock `faces.distance_to_confidence` to avoid loading InsightFace.

### `tests/domain/test_privacy.py` — ≥80% line coverage

| Test | What it covers |
|------|---------------|
| `test_masks_candidato_minor` | `Candidato(es_menor=True, nombre="Juan", apellido="Pérez")` → masked |
| `test_passes_candidato_adult` | `Candidato(es_menor=False, ...)` → unchanged |
| `test_original_not_mutated_candidato` | Verify original `Candidato` still has names after call |
| `test_masks_alerta_familiar_minor` | `AlertaFamiliar(es_menor=True, familiar_nombre="Ana")` → `familiar_nombre=None` |
| `test_passes_alerta_familiar_adult` | `AlertaFamiliar(es_menor=False, familiar_nombre="Carlos")` → preserved |
| `test_masks_persona_admin_minor` | `PersonaAdmin(es_menor=True, ...)` → masked |
| `test_passes_persona_admin_adult` | `PersonaAdmin(es_menor=False, ...)` → preserved |
| `test_none_names_stay_none` | Already-null names remain null (no error) |

### Optional: `tests/repositories/test_persona_repo.py`

**Decision**: In-memory fake, NOT a real Postgres test instance.

**Justification** (unchanged): Repository is mostly SQL passthrough. An in-memory fake exercises the `_row_to_candidato_dict` mapping logic. Real PG integration tests can come later.

The fake will:

- Implement `add` → return canned URLs
- Implement `search_by_estado` → return pre-canned row tuples (simulating `ROW_NUMBER()` best-match-per-person)
- Implement `search_admin` → return pre-canned row tuples (no moderation filter)
- Implement `list_admin` → return pre-canned row tuples
- Implement `set_moderacion` → return canned count
- Implement `delete` → return canned count

| Test | What it covers |
|------|---------------|
| `test_row_to_candidato_dict_mapping` | Distance → coincidencia/confianza via policy |
| `test_row_to_admin_dict_mapping` | Admin aggregation row → PersonaAdmin dict |
| `test_search_returns_best_match_per_person` | Fake returns 1 row per person despite multiple embeddings |
| `test_search_by_estado_filters_moderacion` | Public search only returns 'aprobada' rows |
| `test_search_admin_no_moderacion_filter` | Admin search returns all moderation statuses |
| `test_set_moderacion_returns_count` | Returns number of rows updated |
| `test_delete_returns_photo_count` | Returns number of photos deleted |

---

## 8. Rollout plan

### Pre-deploy checklist

- [ ] `pytest` passes from repository root (all new tests green)
- [ ] `pytest --cov=app/domain --cov=app/repositories --cov-report=term-missing` shows ≥80% coverage on new modules
- [ ] No raw SQL strings for `personas` or `persona_embeddings` tables remain in `app/main.py`
- [ ] `app/main.py` imports from `app.domain` and `app.repositories`
- [ ] Manual smoke test: `POST /buscados` with a known photo → returns candidates; minors have `nombre=None`
- [ ] Manual smoke test: `POST /buscar` (admin) with a known photo → returns candidates with `nombre=None` for minors (Q1 revised)
- [ ] Manual smoke test: `GET /admin/personas` (admin) → minors have `nombre=None` (Q1 revised)
- [ ] Manual smoke test: `POST /encontrados` with `es_menor=True` → names stored in DB, masked in response
- [ ] Manual smoke test: `POST /encontrados` triggers `AlertaFamiliar` with `familiar_nombre=None` when matched person is a minor
- [ ] Manual smoke test: `POST /admin/login` returns token; admin endpoints work with Bearer token
- [ ] Manual smoke test: `PATCH /admin/personas/{id}/moderacion` updates status
- [ ] Manual smoke test: `DELETE /admin/personas/{id}` deletes and cleans up images
- [ ] v0 files deleted (`load_image.py`, `search_image.py`, root `main.py`, `haarcascade_frontalface_default.xml`)
- [ ] `CLAUDE.md` / `AGENTS.md` no longer reference ChromaDB, `LoadImage`, or `SearchImage`
- [ ] `frontend/index.html` has no redundant `es_menor` nulling logic

### Deploy

Standard docker-compose:

```bash
docker-compose pull
docker-compose up -d
```

No database migration is required. The schema is unchanged (the team already has `persona_embeddings`, `moderacion`, and ON DELETE CASCADE).

### Post-deploy validation

```bash
# Health check
curl -s http://localhost:8000/health | jq

# Admin login: get token
TOKEN=$(curl -s -X POST http://localhost:8000/admin/login \
  -H "Content-Type: application/json" \
  -d '{"usuario":"admin","password":"reencuentros2026"}' | jq -r '.token')

# Public search: minors should have nombre=None
curl -X POST http://localhost:8000/buscados \
  -F "files=@known_minor_photo.jpg" \
  -F "nombre=Test" -F "apellido=User" | jq '.coincidencias[] | {nombre, apellido, es_menor}'

# Admin search (with auth): minors should STILL have nombre=None (Q1 revised)
curl -X POST http://localhost:8000/buscar \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@known_minor_photo.jpg" -F "limite=5" | jq '.[] | {nombre, apellido, es_menor}'

# Admin list (with auth): minors should STILL have nombre=None (Q1 revised)
curl -s http://localhost:8000/admin/personas \
  -H "Authorization: Bearer $TOKEN" | jq '.[] | select(.es_menor==true) | {nombre, apellido}'

# Cross-flow alert: check AlertaFamiliar masks minor names
curl -X POST http://localhost:8000/encontrados \
  -F "files=@minor_photo.jpg" \
  -F "es_menor=true" \
  -F "refugio=Test" \
  -F "telefono_responsable=123" \
  -F "doc_responsable=ABC" | jq '.alerta | {familiar_nombre, confianza}'

# Admin endpoint without auth should return 401
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/admin/personas
# Expected: 401
```

### Rollback

1. **Revert the Python code**: `git revert` the PR. Remove `app/domain/` and `app/repositories/`.
2. **Revert the frontend**: Restore `frontend/index.html`.
3. **Database**: No schema migration, so no rollback needed. **Important**: minor names stored in the DB by the new code persist after rollback.
4. **Tests**: Keep `tests/` and dev deps — they are harmless and valuable.
5. **Dead code**: Do NOT restore deleted v0 files.

---

## 9. Open questions / risks for the implementer

### Q1. Minor names: where should they live, and should admin see them?

**Decision (revised)**: Store in DB; mask in ALL regular endpoints (public AND admin). A future change (out of scope) may add a "super-admin with role" endpoint that bypasses the mask. This is applied to `/buscados`, `/encontrados`, `/buscar`, `/admin/personas`, and `AlertaFamiliar`.

### Q2. Cross-flow alert threshold vs. ranking threshold

**Decision**: Same threshold. No separate `alert_threshold`. Both use `MatchingPolicy.is_match()`.

### Q3. Calibration source for MatchingPolicy

**Decision**: Python constants in the policy class, with `threshold` loaded from `Settings.match_threshold`. No YAML/JSON file.

### Q4. Percentage display: sigmoid vs. 1.2 divisor

**Decision (new)**: The `1.2` divisor is obsolete. `MatchingPolicy.match_percentage` delegates to `faces.distance_to_confidence`, a sigmoid calibrated for InsightFace buffalo_l.

### Q5. Face model

**Decision (new)**: InsightFace buffalo_l (ArcFace w600k_r50, 512-dim) with RetinaFace detector. The team already made this change.

### Q6. Multi-embeddings per photo

**Decision (new)**: Each photo generates 1 base + up to 2 augmented embeddings (rotations ±15°), stored in `persona_embeddings`. Search uses `ROW_NUMBER() OVER (PARTITION BY p.person_id ORDER BY pe.embedding <=> %s ASC)`.

### Q7. Auth

**Decision (new)**: `/admin/login` returns a Bearer token (`sha256("reencuentros::" + admin_password)`). All admin endpoints use `Depends(requiere_admin)`. Tests include the Bearer token fixture.

### Q8. Moderation filter

**Decision (new)**: Public searches always filter by `moderacion = 'aprobada'`. Admin can list by `moderacion=pendiente|rechazada|aprobada`. `PATCH /admin/personas/{id}/moderacion` updates the value.

### NEW: How to handle the `DELETE` endpoint's image cleanup?

**Decision**: Move `storage.delete_image(key)` into `PersonaRepository.delete`. The method first fetches `image_key` values, then deletes from the DB, then does best-effort cleanup of each image (try/except per key). The ON DELETE CASCADE handles `persona_embeddings` automatically.

### NEW: How to test the auth fixture without booting DeepFace?

**Decision**: Use unit tests that mock or skip anything requiring DB/DeepFace. The `admin_token` fixture computes `sha256("reencuentros::" + admin_password)` in pure Python. Tests like `test_admin_endpoint_requires_auth_buscar` use `TestClient` and verify the 401 response without needing the lifespan to run (no DB/DeepFace).

### NEW: Where does the moderation default (`'aprobada'`) get applied?

**Decision**: The DB default is set in `_EXTRA_COLS` in `database.py`: `("moderacion", "TEXT NOT NULL DEFAULT 'aprobada'")`. So `INSERT` without specifying `moderacion` works and defaults to `'aprobada'`. The repository's `add` method does NOT need to pass `moderacion` explicitly — the DB default handles it. This is confirmed correct.

### Risk: `es_menor` on `AlertaFamiliar`

Adding `es_menor: bool = False` to `AlertaFamiliar` changes the response model. Existing API consumers will receive an extra field, but this is backward-compatible (adding an optional field doesn't break existing clients). If strict backward compatibility is required, exclude via `model_dump(exclude={"es_menor"})` at the endpoint.

### Risk: Frontend change order

The frontend change (removing `es_menor` nulling) MUST come after the backend privacy serializer is deployed. Deploy backend first, verify, then deploy frontend.

### Risk: `estado` validation at the repository level

The repository uses `WHERE estado = %s` with a raw string. Endpoint handlers validate `estado in ("buscada", "encontrada")` before calling. This validation stays at the endpoint level for this change. A later change could add a DB-level CHECK constraint after a data audit.

### Risk: Tighter review budget

The estimated 700-800 changed lines are near the 800-line review budget. If the diff grows, consider splitting the repository module into a separate PR from the domain modules + endpoint refactor.
