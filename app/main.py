"""Servicio FastAPI de reencuentros — dos flujos + superadmin.

- POST /buscados    (FAMILIAR)   registra una búsqueda y devuelve los encontrados
                                 más parecidos (con % de coincidencia).
- POST /encontrados (RESCATISTA) registra a una persona hallada y avisa si un
                                 familiar ya la estaba buscando.
- POST /buscar      (ADMIN)      compara una foto contra TODA la base.
- GET  /admin/personas           lista todos los registros.
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

# psycopg (database) ANTES que faces (TensorFlow) para evitar crash nativo.
from app.config import get_settings
from app.database import close_pool, get_pool, init_db
from app import faces, storage
from app.schemas import (
    AlertaFamiliar, Candidato, PersonaAdmin, ResultadoBusqueda, ResultadoRegistro,
)

CONTENT_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
CONF_ALTA = 0.40
CONF_MEDIA = 0.50

# columnas que devuelve la búsqueda por estado (orden fijo)
_SEL = ("person_id, estado, es_menor, nombre, apellido, edad, refugio, ubicacion, "
        "telefono_responsable, telefono_contacto, descripcion, image_url")


def nivel_confianza(d: float) -> str:
    if d < CONF_ALTA:
        return "alta"
    if d < CONF_MEDIA:
        return "media"
    return "baja"


def pct_coincidencia(d: float) -> int:
    return max(0, min(100, round((1 - d / 1.2) * 100)))


def gen_codigo() -> str:
    return "REE-" + uuid.uuid4().hex[:8].upper()


async def _embedding_de_fotos(files: list[UploadFile]):
    """Devuelve (lista de (bytes, content_type), embedding de la 1ª foto válida)."""
    fotos, embedding = [], None
    for f in files:
        data = await f.read()
        if not data:
            continue
        ct = f.content_type or "image/jpeg"
        if embedding is None:
            try:
                embedding = faces.embedding_from_bytes(data)
            except ValueError:
                continue  # sin rostro: se omite
        fotos.append((data, ct))
    return fotos, embedding


def _insertar_fotos(conn, person_id, datos: dict, fotos, embedding):
    """Inserta una fila por foto (todas con el mismo person_id) y devuelve URLs."""
    urls = []
    for i, (data, ct) in enumerate(fotos):
        ext = CONTENT_EXT.get(ct, "jpg")
        foto_id = uuid.uuid4()
        key = f"personas/{foto_id}.{ext}"
        url = storage.upload_image(data, key, ct)
        conn.execute(
            """
            INSERT INTO personas
              (id, person_id, estado, es_menor, nombre, apellido, edad, doc_tipo,
               doc_numero, telefono_contacto, refugio, telefono_responsable,
               doc_responsable, descripcion, ubicacion, codigo, image_url, image_key, embedding)
            VALUES (%(id)s, %(pid)s, %(estado)s, %(menor)s, %(nombre)s, %(apellido)s, %(edad)s,
                    %(doc_tipo)s, %(doc_numero)s, %(tel_contacto)s, %(refugio)s, %(tel_resp)s,
                    %(doc_resp)s, %(descripcion)s, %(ubicacion)s, %(codigo)s, %(url)s, %(key)s, %(emb)s)
            """,
            {**datos, "id": foto_id, "pid": person_id, "url": url, "key": key, "emb": embedding},
        )
        urls.append(url)
    return urls


def _buscar_por_estado(conn, embedding, estado: str, limite: int):
    return conn.execute(
        f"""
        SELECT {_SEL}, distancia FROM (
            SELECT DISTINCT ON (person_id) {_SEL}, embedding <=> %s AS distancia
            FROM personas WHERE estado = %s AND moderacion = 'aprobada'
            ORDER BY person_id, embedding <=> %s ASC
        ) t ORDER BY distancia ASC LIMIT %s
        """,
        (embedding, estado, embedding, limite),
    ).fetchall()


def _fila_a_candidato(r) -> Candidato:
    (person_id, estado, es_menor, nombre, apellido, edad, refugio, ubicacion,
     tel_resp, tel_contacto, descripcion, image_url, distancia) = r
    d = float(distancia)
    return Candidato(
        person_id=str(person_id), estado=estado, es_menor=bool(es_menor),
        nombre=None if es_menor else nombre,  # protocolo de protección
        apellido=None if es_menor else apellido, edad=edad,
        refugio=refugio, ubicacion=ubicacion or refugio,
        telefono=tel_resp or tel_contacto, descripcion=descripcion,
        image_url=image_url, distancia=round(d, 4),
        coincidencia=pct_coincidencia(d), confianza=nivel_confianza(d),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    get_pool()
    faces.warmup()
    yield
    close_pool()


tags = [
    {"name": "familiar", "description": "Flujo del familiar que busca a alguien."},
    {"name": "rescatista", "description": "Flujo de quien encontró a una persona."},
    {"name": "admin", "description": "Superadmin: buscar y comparar imágenes."},
    {"name": "sistema", "description": "Estado del servicio."},
]

DESCRIPTION = """
API de **reconocimiento facial** para reunir personas desaparecidas con sus familias.

Todas las peticiones de registro/búsqueda son **`multipart/form-data`** (porque suben
foto). La foto va en el campo **`files`** (puedes mandar varias del mismo registro).

---

### 🟣 Flujo FAMILIAR — `POST /buscados`
Un familiar sube la foto de a quién busca. Se registra como *buscada* y se devuelve la
**lista de personas ya encontradas** ordenadas por parecido.

| Campo | Tipo | Obligatorio | Ejemplo |
|---|---|---|---|
| `files` | archivo(s) | **Sí** (con rostro) | foto.jpg |
| `nombre` | texto | no* | `María` |
| `apellido` | texto | no | `Pérez` |
| `edad` | texto | no | `8` |
| `doc_tipo` | texto | no | `V` |
| `doc_numero` | texto | no* | `12345678` |
| `telefono_contacto` | texto | no | `0412-1234567` |

\\* Manda **al menos** `nombre` o `doc_numero` (validación).

### 🟢 Flujo RESCATISTA — `POST /encontrados`
Quien encontró a alguien lo registra. Si un familiar ya lo buscaba, la respuesta trae
una **alerta** con el nombre y teléfono del familiar.

| Campo | Tipo | Obligatorio | Ejemplo |
|---|---|---|---|
| `files` | archivo(s) | **Sí** (con rostro) | foto.jpg |
| `es_menor` | bool | no (def. `false`) | `true` |
| `nombre` | texto | no (se ignora si `es_menor`) | `Juan` |
| `apellido` | texto | no (se ignora si `es_menor`) | `Gómez` |
| `doc_tipo` / `doc_numero` | texto | no | `V` / `87654321` |
| `refugio` | texto | **Sí** | `Refugio Central, Caracas` |
| `ubicacion` | texto | no | `Plaza Bolívar` |
| `telefono_responsable` | texto | **Sí** | `0414-9999999` |
| `doc_responsable` | texto | **Sí si `es_menor`** | `V-11111111` |
| `descripcion` | texto | no | `cabello castaño, 1.20 m` |

> **Protocolo de menor:** si `es_menor=true`, el `nombre`/`apellido` NO se guardan y en
> las búsquedas aparece como *"Menor protegido"*.

### 🛡️ SUPERADMIN
- `POST /buscar` — comparar una foto contra TODA la base (campo `file`, `limite`, `estado`).
- `GET /admin/personas` — listar registros.

---

### Cómo interpretar la respuesta de búsqueda
Cada candidato trae:
- **`coincidencia`** (0-100): porcentaje de parecido para mostrar al usuario.
- **`confianza`**: `alta` (<0.40, casi seguro) · `media` (0.40-0.50, revisar) · `baja`.
- **`distancia`**: valor técnico (menor = más parecido; 0 = idéntico).
- **`refugio`, `ubicacion`, `telefono`**: datos para el reencuentro (el botón *"Es mi familiar"*).
"""

app = FastAPI(
    title="Reencuentros — Reconocimiento facial",
    description=DESCRIPTION,
    version="2.0.0", openapi_tags=tags, lifespan=lifespan,
)


@app.get("/health", tags=["sistema"], summary="Estado del servicio")
def health():
    return {"status": "ok"}


@app.post("/buscados", response_model=ResultadoBusqueda, status_code=201, tags=["familiar"],
          summary="Familiar: registrar búsqueda y ver coincidencias")
async def registrar_busqueda(
    files: list[UploadFile] = File(..., description="Foto(s) del rostro de la persona buscada (obligatorio)."),
    nombre: str | None = Form(None), apellido: str | None = Form(None),
    edad: str | None = Form(None), doc_tipo: str | None = Form(None),
    doc_numero: str | None = Form(None),
    telefono_contacto: str | None = Form(None, description="Teléfono del familiar para el reencuentro."),
):
    fotos, embedding = await _embedding_de_fotos(files)
    # --- Validaciones ---
    if not fotos:
        raise HTTPException(400, "Debes subir al menos una foto.")
    if embedding is None:
        raise HTTPException(422, "No se detectó ningún rostro en la(s) foto(s).")
    if not (doc_numero or (nombre and nombre.strip())):
        raise HTTPException(422, "Indica al menos el nombre o el número de identificación.")

    person_id = uuid.uuid4()
    codigo = gen_codigo()
    datos = dict(estado="buscada", menor=False, nombre=nombre, apellido=apellido, edad=edad,
                 doc_tipo=doc_tipo, doc_numero=doc_numero, tel_contacto=telefono_contacto,
                 refugio=None, tel_resp=None, doc_resp=None, descripcion=None,
                 ubicacion=None, codigo=codigo)
    with get_pool().connection() as conn:
        _insertar_fotos(conn, person_id, datos, fotos, embedding)
        encontrados = _buscar_por_estado(conn, embedding, "encontrada", 25)
        conn.commit()

    candidatos = [_fila_a_candidato(r) for r in encontrados]
    return ResultadoBusqueda(codigo=codigo, total=len(candidatos), coincidencias=candidatos)


@app.post("/encontrados", response_model=ResultadoRegistro, status_code=201, tags=["rescatista"],
          summary="Rescatista: registrar persona encontrada")
async def registrar_encontrado(
    files: list[UploadFile] = File(..., description="Foto(s) del rostro de la persona encontrada (obligatorio)."),
    es_menor: bool = Form(False, description="Activar si es menor de edad (oculta datos sensibles)."),
    nombre: str | None = Form(None), apellido: str | None = Form(None),
    doc_tipo: str | None = Form(None), doc_numero: str | None = Form(None),
    refugio: str | None = Form(None, description="Refugio donde se encuentra."),
    ubicacion: str | None = Form(None, description="Dónde se encontró a la persona."),
    telefono_responsable: str | None = Form(None, description="Teléfono del responsable."),
    doc_responsable: str | None = Form(None, description="Identificación del responsable."),
    descripcion: str | None = Form(None, description="Descripción física básica."),
):
    fotos, embedding = await _embedding_de_fotos(files)
    # --- Validaciones ---
    if not fotos:
        raise HTTPException(400, "Debes subir al menos una foto.")
    if embedding is None:
        raise HTTPException(422, "No se detectó ningún rostro en la(s) foto(s).")
    if not refugio or not refugio.strip():
        raise HTTPException(422, "El refugio actual es obligatorio.")
    if not telefono_responsable or not telefono_responsable.strip():
        raise HTTPException(422, "El teléfono del responsable es obligatorio.")
    if es_menor and not (doc_responsable and doc_responsable.strip()):
        raise HTTPException(422, "Para un menor, la identificación del responsable es obligatoria.")

    person_id = uuid.uuid4()
    codigo = gen_codigo()
    datos = dict(estado="encontrada", menor=es_menor,
                 nombre=None if es_menor else nombre,        # protocolo de protección
                 apellido=None if es_menor else apellido,
                 edad=None, doc_tipo=doc_tipo, doc_numero=doc_numero, tel_contacto=None,
                 refugio=refugio, tel_resp=telefono_responsable, doc_resp=doc_responsable,
                 descripcion=descripcion, ubicacion=ubicacion, codigo=codigo)
    with get_pool().connection() as conn:
        _insertar_fotos(conn, person_id, datos, fotos, embedding)
        buscados = _buscar_por_estado(conn, embedding, "buscada", 1)
        conn.commit()

    alerta = None
    if buscados:
        r = buscados[0]
        d = float(r[-1])
        if d < CONF_MEDIA:  # coincidencia real (alta/media)
            alerta = AlertaFamiliar(
                person_id=str(r[0]), familiar_nombre=r[3], familiar_telefono=r[9],
                image_url=r[11], coincidencia=pct_coincidencia(d), confianza=nivel_confianza(d),
            )
    return ResultadoRegistro(codigo=codigo, person_id=str(person_id), alerta=alerta)


@app.post("/buscar", response_model=list[Candidato], tags=["admin"],
          summary="Superadmin: comparar una foto contra TODA la base")
async def buscar_admin(
    file: UploadFile = File(...),
    limite: int = Form(25),
    estado: str | None = Form(None, description="Filtrar por 'buscada' o 'encontrada' (vacío = todas)."),
):
    data = await file.read()
    try:
        embedding = faces.embedding_from_bytes(data)
    except ValueError as e:
        raise HTTPException(422, str(e))
    filtra = estado in ("buscada", "encontrada")
    where = "WHERE estado = %s" if filtra else ""
    params = (embedding, estado, embedding, limite) if filtra else (embedding, embedding, limite)
    with get_pool().connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {_SEL}, distancia FROM (
                SELECT DISTINCT ON (person_id) {_SEL}, embedding <=> %s AS distancia
                FROM personas {where}
                ORDER BY person_id, embedding <=> %s ASC
            ) t ORDER BY distancia ASC LIMIT %s
            """,
            params,
        ).fetchall()
    return [_fila_a_candidato(r) for r in rows]


@app.get("/admin/personas", response_model=list[PersonaAdmin], tags=["admin"],
         summary="Superadmin: listar registros")
def listar(limite: int = 100, estado: str | None = None, moderacion: str | None = None):
    """Lista registros. Filtra por estado y/o moderación (para revisar/aprobar)."""
    conds, args = [], []
    if estado in ("buscada", "encontrada"):
        conds.append("estado = %s")
        args.append(estado)
    if moderacion in ("aprobada", "rechazada", "pendiente"):
        conds.append("moderacion = %s")
        args.append(moderacion)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    args.append(limite)
    with get_pool().connection() as conn:
        rows = conn.execute(
            f"""
            SELECT person_id, max(estado), bool_or(es_menor), max(nombre), max(apellido),
                   max(edad), max(doc_numero), max(refugio), max(ubicacion),
                   coalesce(max(telefono_responsable), max(telefono_contacto)),
                   max(codigo), max(moderacion), array_agg(image_url), min(created_at)
            FROM personas {where}
            GROUP BY person_id ORDER BY min(created_at) DESC LIMIT %s
            """,
            tuple(args),
        ).fetchall()
    return [
        PersonaAdmin(
            person_id=str(r[0]), estado=r[1], es_menor=bool(r[2]), nombre=r[3], apellido=r[4],
            edad=r[5], doc=r[6], refugio=r[7], ubicacion=r[8], telefono=r[9], codigo=r[10],
            moderacion=r[11], fotos=list(r[12]), created_at=r[13],
        )
        for r in rows
    ]


@app.patch("/admin/personas/{person_id}/moderacion", tags=["admin"],
           summary="Aprobar / rechazar una publicación")
def moderar(person_id: str, valor: str):
    """`valor` = `aprobada` | `rechazada` | `pendiente`. Las rechazadas no aparecen en búsquedas."""
    if valor not in ("aprobada", "rechazada", "pendiente"):
        raise HTTPException(400, "valor debe ser 'aprobada', 'rechazada' o 'pendiente'")
    with get_pool().connection() as conn:
        n = conn.execute(
            "UPDATE personas SET moderacion = %s WHERE person_id = %s", (valor, person_id)
        ).rowcount
        conn.commit()
    if not n:
        raise HTTPException(404, "No existe esa persona")
    return {"person_id": person_id, "moderacion": valor, "fotos_actualizadas": n}


@app.delete("/admin/personas/{person_id}", tags=["admin"],
            summary="Eliminar una publicación (contenido indebido)")
def eliminar(person_id: str):
    """Borra la persona, sus fotos del almacenamiento y sus filas de la BD."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT image_key FROM personas WHERE person_id = %s", (person_id,)
        ).fetchall()
        if not rows:
            raise HTTPException(404, "No existe esa persona")
        for (key,) in rows:
            try:
                storage.delete_image(key)
            except Exception:
                pass
        conn.execute("DELETE FROM personas WHERE person_id = %s", (person_id,))
        conn.commit()
    return {"person_id": person_id, "eliminada": True, "fotos": len(rows)}
