from datetime import datetime

from pydantic import BaseModel, Field


class LoginBody(BaseModel):
    usuario: str = Field("admin", examples=["admin"])
    password: str = Field(..., examples=["reencuentros2026"])


class LoginResp(BaseModel):
    token: str
    tipo: str = "Bearer"


class Candidato(BaseModel):
    """Una persona candidata de una búsqueda, con su grado de parecido."""

    person_id: str
    estado: str = Field(..., description="'buscada' o 'encontrada'.")
    es_menor: bool = False
    nombre: str | None = Field(None, description="Oculto si es menor (protocolo de protección).")
    apellido: str | None = None
    edad: str | None = None
    refugio: str | None = Field(None, description="Refugio donde se encuentra (si fue encontrada).")
    ubicacion: str | None = Field(None, description="Última ubicación conocida / dónde se encontró.")
    telefono: str | None = Field(None, description="Teléfono de contacto para el reencuentro.")
    descripcion: str | None = None
    image_url: str
    distancia: float = Field(..., description="Distancia coseno (menor = más parecido).")
    coincidencia: int = Field(..., description="Porcentaje de coincidencia (0-100).")
    confianza: str = Field(..., description="'alta' | 'media' | 'baja'.")


class ResultadoBusqueda(BaseModel):
    """Respuesta del flujo FAMILIAR: su código + lista de candidatos."""

    codigo: str = Field(..., description="Código del registro de búsqueda generado.")
    total: int
    coincidencias: list[Candidato]


class AlertaFamiliar(BaseModel):
    """Aviso cuando un RESCATISTA registra a alguien que un familiar ya buscaba."""

    person_id: str
    familiar_nombre: str | None = None
    familiar_telefono: str | None = None
    image_url: str
    coincidencia: int
    confianza: str


class ResultadoRegistro(BaseModel):
    """Respuesta del flujo RESCATISTA: código + posible alerta de coincidencia."""

    codigo: str = Field(..., description="Código de registro generado.")
    person_id: str
    alerta: AlertaFamiliar | None = Field(None, description="Familiar que ya buscaba a esta persona, si hay match.")


class PersonaAdmin(BaseModel):
    """Vista de superadmin: registro con sus datos y fotos."""

    person_id: str
    estado: str
    es_menor: bool
    nombre: str | None = None
    apellido: str | None = None
    edad: str | None = None
    doc: str | None = None
    refugio: str | None = None
    ubicacion: str | None = None
    telefono: str | None = None
    codigo: str | None = None
    moderacion: str = "aprobada"
    fotos: list[str]
    created_at: datetime
