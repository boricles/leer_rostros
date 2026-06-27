from datetime import datetime

from pydantic import BaseModel, Field


class PersonaOut(BaseModel):
    """Persona registrada (puede tener varias fotos)."""

    person_id: str = Field(..., description="Identificador de la persona.", examples=["3ad0cfd3-a08e-4c97-8cc5-1785051d09f0"])
    nombre: str | None = Field(None, description="Nombre de la persona (opcional).", examples=["José Pérez"])
    ci: str | None = Field(None, description="Cédula o documento de identidad (opcional).", examples=["V-12345678"])
    rol: str | None = Field(None, description="Rol o nota libre (opcional).", examples=[None])
    estado: str = Field(..., description="Estado: 'buscada' (un familiar la busca) o 'encontrada' (un rescatista la halló).", examples=["desaparecida"])
    fotos: list[str] = Field(..., description="URLs públicas de las fotos de la persona en el bucket.")
    created_at: datetime = Field(..., description="Fecha y hora de registro (UTC).")


class Coincidencia(BaseModel):
    """Persona candidata de una búsqueda, con su mejor foto coincidente."""

    person_id: str = Field(..., description="Identificador de la persona.")
    nombre: str | None = Field(None, description="Nombre de la persona.")
    ci: str | None = Field(None, description="Cédula o documento de identidad.")
    rol: str | None = Field(None, description="Rol o nota libre.")
    estado: str = Field(..., description="Estado de la persona.")
    image_url: str = Field(..., description="Foto registrada que mejor coincide con la búsqueda.")
    distancia: float = Field(..., description="Distancia coseno (menor = más parecido; 0 = idéntico).", examples=[0.256])
    es_match: bool = Field(..., description="True si la distancia está por debajo del umbral.", examples=[True])
    confianza: str = Field(..., description="Nivel: 'alta' (casi seguro), 'media' (posible, revisar) o 'baja'.", examples=["alta"])


class ResultadoBusqueda(BaseModel):
    """Resultado de una búsqueda: una persona por candidato, ordenadas por parecido."""

    umbral: float = Field(..., description="Umbral de coincidencia (distancia < umbral = match).", examples=[0.55])
    coincidencias: list[Coincidencia] = Field(..., description="Personas candidatas, de la más parecida a la menos.")
