"""Shared utilities used across bounded contexts (personas, reportes, …)."""

from app.shared._exceptions import (
    ModificacionInvalidaError,
    PersonaNotFoundError,
    PersonaValidationError,
    RostroNoDetectadoError,
)
from app.shared._helpers import LIMITE_MAX, ProcessedPhotos, _embedding_consulta, _gen_codigo

__all__ = [
    "LIMITE_MAX",
    "ModificacionInvalidaError",
    "PersonaNotFoundError",
    "PersonaValidationError",
    "ProcessedPhotos",
    "RostroNoDetectadoError",
    "_embedding_consulta",
    "_gen_codigo",
]
