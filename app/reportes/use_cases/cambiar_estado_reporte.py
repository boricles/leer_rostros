"""CambiarEstadoReporte use case: ADMIN moderation flow for report status."""

from uuid import UUID

from app.reportes.repositories.reporte import ReporteRepository
from app.shared._exceptions import (
    ModificacionInvalidaError,
    PersonaNotFoundError,
    PersonaValidationError,
)


VALID_ESTADOS = ("pendiente", "revisado", "resuelto", "descartado")


class CambiarEstadoReporte:
    """ADMIN flow: change the lifecycle status of a report."""

    def __init__(self, repo: ReporteRepository):
        self._repo = repo

    def execute(self, *, reporte_id: str, valor: str) -> dict:
        """Update `estado` for one report.

        Args:
            reporte_id: UUID string of the report to update.
            valor: New status — one of `'pendiente' | 'revisado' | 'resuelto' | 'descartado'`.

        Returns:
            Dict with `id` and `estado`.

        Raises:
            ModificacionInvalidaError: If `valor` is not one of the valid statuses.
            PersonaValidationError: If `reporte_id` is not a valid UUID.
            PersonaNotFoundError: If no report matches the given `reporte_id`.
        """
        if valor not in VALID_ESTADOS:
            raise ModificacionInvalidaError(
                f"valor debe ser uno de {VALID_ESTADOS}"
            )

        try:
            rid = UUID(reporte_id)
        except (ValueError, AttributeError):
            raise PersonaValidationError("reporte_id inválido.")

        n = self._repo.set_estado(rid, valor)
        if not n:
            raise PersonaNotFoundError("No existe ese reporte")

        return {"id": reporte_id, "estado": valor}
