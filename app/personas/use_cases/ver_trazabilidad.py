"""VerTrazabilidad use case: histórico completo de una persona (vista admin)."""

from app.personas.repositories.persona import PersonaRepository
from app.schemas import EventoHistorial, TrazaPersona
from app.shared._exceptions import PersonaNotFoundError


class VerTrazabilidad:
    """Devuelve el histórico de avistamientos (trazabilidad) de una persona."""

    def __init__(self, repo: PersonaRepository):
        self._repo = repo

    def execute(self, *, person_id: str) -> TrazaPersona:
        """Lista los eventos del histórico en orden cronológico.

        Raises:
            PersonaNotFoundError: si el person_id no existe (HTTP 404).
        """
        if not self._repo.persona_exists(person_id):
            raise PersonaNotFoundError("No existe esa persona.")

        eventos = self._repo.list_historial(person_id)
        return TrazaPersona(
            person_id=person_id,
            total_eventos=len(eventos),
            eventos=[EventoHistorial(**e) for e in eventos],
        )
