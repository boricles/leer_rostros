"""ListarReportesAdmin use case: ADMIN list flow for reports."""

from app.reportes.repositories.reporte import ReporteRepository
from app.schemas import ReporteAdmin


class ListarReportesAdmin:
    """ADMIN flow: list received reports (falla + publicacion) with optional filters."""

    def __init__(self, repo: ReporteRepository):
        self._repo = repo

    def execute(
        self,
        *,
        tipo: str | None,
        estado: str | None,
        limite: int = 100,
    ) -> list[ReporteAdmin]:
        """List reports ordered by most recent first.

        Args:
            tipo: Optional filter — `'falla'` or `'publicacion'`. Other values are ignored.
            estado: Optional filter — one of `'pendiente' | 'revisado' | 'resuelto' | 'descartado'`.
            limite: Maximum reports to return (default 100).

        Returns:
            List of ReporteAdmin. Publication reports carry `pub_nombre`, `pub_estado`,
            `pub_image_url`, and `pub_moderacion` (snapshot of the publication at
            query time).
        """
        results = self._repo.list_admin(tipo=tipo, estado=estado, limite=limite)
        return [ReporteAdmin(**d) for d in results]
