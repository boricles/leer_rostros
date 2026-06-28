"""RegistrarPublicacion use case: public flow for reporting an inadequate publication."""

from uuid import UUID

from app.reportes.repositories.reporte import ReporteRepository
from app.schemas import ReportePublicacionIn
from app.shared._exceptions import PersonaNotFoundError, PersonaValidationError


class RegistrarPublicacion:
    """Public flow: register a report against an inadequate publication."""

    def __init__(self, repo: ReporteRepository):
        self._repo = repo

    def execute(self, datos: ReportePublicacionIn) -> dict:
        """Persist a `publicacion` report. Returns a ReporteCreado-shaped dict.

        The report does NOT auto-hide the publication; it queues the report for
        the superadmin to review (they can reject or delete from the admin UI).

        Args:
            datos: Pydantic input model with `person_id`, `descripcion`, `contacto?`.

        Returns:
            Dict with `id`, `tipo='publicacion'`, `estado='pendiente'`, `created_at`.

        Raises:
            PersonaValidationError: If `person_id` is not a valid UUID or
                `descripcion` is empty (HTTP 422).
            PersonaNotFoundError: If no persona matches the given `person_id`
                (HTTP 404 — preserves the legacy endpoint contract).
        """
        try:
            pid = UUID(datos.person_id)
        except (ValueError, AttributeError):
            raise PersonaValidationError("person_id inválido.")

        descripcion = datos.descripcion.strip()
        if not descripcion:
            raise PersonaValidationError("La descripción no puede estar vacía.")

        if not self._repo.persona_exists(pid):
            raise PersonaNotFoundError(
                "No existe la publicación que intentas reportar."
            )

        return self._repo.add_publicacion(
            descripcion=descripcion,
            person_id=pid,
            contacto=datos.contacto,
        )
