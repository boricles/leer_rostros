"""Menores privacy protocol: mask names at API response boundary."""

from typing import TypeVar

from app.schemas import AlertaFamiliar, Candidato, PersonaAdmin

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

    # Candidato and PersonaAdmin: mask nombre and apellido
    return obj.model_copy(update={"nombre": None, "apellido": None})
