"""Servicio FastAPI de reconocimiento facial para reencuentros de personas.

Una persona puede registrarse con VARIAS fotos (más ángulos = más probabilidad
de encontrarla). Al buscar, se agrupa por persona y se devuelve su mejor
coincidencia.
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

# IMPORTANTE: psycopg (database) debe importarse ANTES que faces (TensorFlow),
# o hay un crash nativo "free(): invalid pointer" por conflicto de librerías.
from app.config import get_settings
from app.database import close_pool, get_pool, init_db
from app import faces, storage
from app.schemas import Coincidencia, PersonaOut, ResultadoBusqueda

CONTENT_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

# Bandas de confianza calibradas para Facenet512 (misma persona <=0.469,
# distintas >=0.549). Menor distancia = más parecido.
CONF_ALTA = 0.40
CONF_MEDIA = 0.50


def nivel_confianza(distancia: float) -> str:
    if distancia < CONF_ALTA:
        return "alta"
    if distancia < CONF_MEDIA:
        return "media"
    return "baja"


DESCRIPTION = """
API de **reconocimiento facial** para reunir personas desaparecidas con sus familias.

Cada foto se convierte en un **vector facial** (DeepFace **SFace + retinaface**) y se
compara por **distancia coseno** sobre **Postgres + pgvector**. Las imágenes se guardan
en **DigitalOcean Spaces**.

### Flujo
1. **Registrar** a la persona — puede subir **varias fotos** de la misma persona.
2. **Buscar** coincidencias subiendo otra foto.

### Interpretación
- `distancia` menor = más parecido (0 = idéntico).
- `confianza`: **alta** (<0.45), **media** (0.45–0.60, revisar) o **baja**.
- Resultados **ordenados**; la decisión final la toma una persona.
"""

tags_metadata = [
    {"name": "personas", "description": "Registrar y listar personas (con una o varias fotos)."},
    {"name": "búsqueda", "description": "Reconocimiento facial: encontrar coincidencias por foto."},
    {"name": "sistema", "description": "Estado y salud del servicio."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    get_pool()
    faces.warmup()  # pre-carga modelo + detector (evita cold start)
    yield
    close_pool()


app = FastAPI(
    title="Reencuentros — Reconocimiento facial",
    description=DESCRIPTION,
    version="1.1.0",
    openapi_tags=tags_metadata,
    contact={"name": "Proyecto Reencuentros"},
    license_info={"name": "Uso humanitario"},
    lifespan=lifespan,
)


@app.get("/health", tags=["sistema"], summary="Estado del servicio")
def health():
    """Devuelve `{"status": "ok"}` si el servicio está operativo."""
    return {"status": "ok"}


@app.post(
    "/personas",
    response_model=PersonaOut,
    status_code=201,
    tags=["personas"],
    summary="Registrar una persona (una o varias fotos)",
    response_description="La persona registrada con las URLs de sus fotos.",
)
async def registrar_persona(
    files: list[UploadFile] = File(..., description="Una o varias fotos de la MISMA persona (JPEG/PNG/WebP)."),
    nombre: str | None = Form(None, description="Nombre de la persona (opcional)."),
    ci: str | None = Form(None, description="Cédula o documento (opcional)."),
    rol: str | None = Form(None, description="Rol o nota libre (opcional)."),
    estado: str = Form("desaparecida", description="'buscada' (la busca un familiar) o 'encontrada' (la halló un rescatista)."),
):
    """Registra una persona con una o varias fotos. Todas comparten un mismo
    `person_id`; en la búsqueda basta con que UNA coincida para identificarla."""
    person_id = uuid.uuid4()
    fotos: list[str] = []
    created_at = None

    with get_pool().connection() as conn:
        for file in files:
            data = await file.read()
            content_type = file.content_type or "image/jpeg"
            ext = CONTENT_EXT.get(content_type, "jpg")
            try:
                embedding = faces.embedding_from_bytes(data)
            except ValueError:
                continue  # foto ilegible: se omite, no rompe el registro

            foto_id = uuid.uuid4()
            key = f"personas/{foto_id}.{ext}"
            image_url = storage.upload_image(data, key, content_type)
            row = conn.execute(
                """
                INSERT INTO personas (id, person_id, nombre, ci, rol, estado, image_url, image_key, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING created_at
                """,
                (foto_id, person_id, nombre, ci, rol, estado, image_url, key, embedding),
            ).fetchone()
            created_at = row[0]
            fotos.append(image_url)
        conn.commit()

    if not fotos:
        raise HTTPException(status_code=400, detail="Ninguna foto tenía un rostro procesable.")

    return PersonaOut(
        person_id=str(person_id), nombre=nombre, ci=ci, rol=rol,
        estado=estado, fotos=fotos, created_at=created_at,
    )


@app.post(
    "/buscar",
    response_model=ResultadoBusqueda,
    tags=["búsqueda"],
    summary="Buscar coincidencias por foto",
    response_description="Una persona por candidato, ordenadas por parecido.",
)
async def buscar(
    file: UploadFile = File(..., description="Foto del rostro a buscar (JPEG/PNG/WebP)."),
    limite: int = Form(10, description="Máximo de personas candidatas a devolver."),
):
    """Calcula el vector de la foto y devuelve las personas más parecidas. Si una
    persona tiene varias fotos, se toma su mejor coincidencia (una sola entrada)."""
    data = await file.read()
    try:
        embedding = faces.embedding_from_bytes(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    s = get_settings()
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT person_id, nombre, ci, rol, estado, image_url, distancia FROM (
                SELECT DISTINCT ON (person_id)
                       person_id, nombre, ci, rol, estado, image_url,
                       embedding <=> %s AS distancia
                FROM personas
                ORDER BY person_id, embedding <=> %s ASC
            ) mejor_por_persona
            ORDER BY distancia ASC
            LIMIT %s
            """,
            (embedding, embedding, limite),
        ).fetchall()

    coincidencias = [
        Coincidencia(
            person_id=str(r[0]), nombre=r[1], ci=r[2], rol=r[3], estado=r[4],
            image_url=r[5], distancia=float(r[6]),
            es_match=float(r[6]) < s.match_threshold,
            confianza=nivel_confianza(float(r[6])),
        )
        for r in rows
    ]
    return ResultadoBusqueda(umbral=s.match_threshold, coincidencias=coincidencias)


@app.get(
    "/personas",
    response_model=list[PersonaOut],
    tags=["personas"],
    summary="Listar personas registradas",
    response_description="Personas registradas (con todas sus fotos), de la más reciente a la más antigua.",
)
def listar_personas(limite: int = 50):
    """Lista las personas registradas, agrupando las fotos de cada una."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT person_id,
                   max(nombre) AS nombre, max(ci) AS ci, max(rol) AS rol,
                   max(estado) AS estado, array_agg(image_url) AS fotos,
                   min(created_at) AS created_at
            FROM personas
            GROUP BY person_id
            ORDER BY min(created_at) DESC
            LIMIT %s
            """,
            (limite,),
        ).fetchall()
    return [
        PersonaOut(
            person_id=str(r[0]), nombre=r[1], ci=r[2], rol=r[3],
            estado=r[4], fotos=list(r[5]), created_at=r[6],
        )
        for r in rows
    ]
