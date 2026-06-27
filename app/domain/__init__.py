"""Domain module barrel - re-exports public types."""

from app.domain.matching import MatchingPolicy, Confianza
from app.domain.privacy import MenoresPrivacy
from app.domain.persona import PersonaBase, Estado, Foto

__all__ = [
    "MatchingPolicy",
    "Confianza",
    "MenoresPrivacy",
    "PersonaBase",
    "Estado",
    "Foto",
]
