"""Persona domain entity."""

from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class Estado(str, Enum):
    """Valid estados for a persona."""

    BUSCADA = "buscada"
    ENCONTRADA = "encontrada"


@dataclass(frozen=True)
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
    encontrado_por: str | None = None  # nombre de quien encontró a la persona
    photos: list[str] = Field(default_factory=list)  # list of image_urls
    distancia: float | None = None  # only populated for search results
    moderacion: str = "aprobada"
