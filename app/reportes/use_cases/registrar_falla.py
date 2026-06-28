"""RegistrarFalla use case: public flow for reporting website bugs."""

from app.reportes.repositories.reporte import ReporteRepository
from app.schemas import ReporteFallaIn
from app.shared._exceptions import PersonaValidationError


class RegistrarFalla:
    """Public flow: register a bug/failure report about the website."""

    def __init__(self, repo: ReporteRepository):
        self._repo = repo

    def execute(self, datos: ReporteFallaIn) -> dict:
        """Persist a `falla` report. Returns a ReporteCreado-shaped dict.

        Args:
            datos: Pydantic input model from the public endpoint.

        Returns:
            Dict with `id`, `tipo='falla'`, `estado='pendiente'`, `created_at`.

        Raises:
            PersonaValidationError: If `descripcion` is empty after strip.
        """
        descripcion = datos.descripcion.strip()
        if not descripcion:
            raise PersonaValidationError("La descripción no puede estar vacía.")

        return self._repo.add_falla(
            descripcion=descripcion,
            url=datos.url,
            contacto=datos.contacto,
        )
