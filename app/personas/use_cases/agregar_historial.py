"""AgregarHistorial use case: un rescatista registra un nuevo avistamiento."""

from app.personas.repositories.persona import PersonaRepository
from app.schemas import EventoHistorial, ResultadoHistorial
from app.shared._exceptions import PersonaNotFoundError, PersonaValidationError


class AgregarHistorial:
    """Agrega un evento de trazabilidad a una persona ya registrada.

    Pensado para cuando un rescatista modifica/actualiza dónde está la persona:
    se guarda el evento (con su timestamp) y se actualiza su ubicación actual.
    """

    def __init__(self, repo: PersonaRepository):
        self._repo = repo

    def execute(
        self,
        *,
        person_id: str,
        refugio: str | None = None,
        ubicacion: str | None = None,
        encontrado_por: str | None = None,
        telefono_responsable: str | None = None,
        nota: str | None = None,
    ) -> ResultadoHistorial:
        """Registra un avistamiento en el histórico de `person_id`.

        Raises:
            PersonaNotFoundError: si el person_id no existe (HTTP 404).
            PersonaValidationError: si no se aporta ni refugio ni ubicación (HTTP 422).
        """
        if not self._repo.persona_exists(person_id):
            raise PersonaNotFoundError("No existe esa persona.")

        tiene_lugar = (refugio and refugio.strip()) or (ubicacion and ubicacion.strip())
        if not tiene_lugar:
            raise PersonaValidationError(
                "Indica al menos el refugio o la ubicación del avistamiento."
            )

        evento = self._repo.add_historial(
            person_id,
            refugio=refugio,
            ubicacion=ubicacion,
            encontrado_por=encontrado_por,
            telefono_responsable=telefono_responsable,
            nota=nota,
            actualizar_actual=True,
        )
        total = self._repo.count_historial(person_id)
        return ResultadoHistorial(
            person_id=person_id,
            evento=EventoHistorial(**evento),
            total_eventos=total,
        )
