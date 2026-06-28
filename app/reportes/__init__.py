"""Reportes bounded context — repository + use cases for the reportes table."""

from app.reportes.repositories.reporte import ReporteRepository
from app.reportes.use_cases.cambiar_estado_reporte import CambiarEstadoReporte
from app.reportes.use_cases.listar_reportes_admin import ListarReportesAdmin
from app.reportes.use_cases.registrar_falla import RegistrarFalla
from app.reportes.use_cases.registrar_publicacion import RegistrarPublicacion

__all__ = [
    "CambiarEstadoReporte",
    "ListarReportesAdmin",
    "RegistrarFalla",
    "RegistrarPublicacion",
    "ReporteRepository",
]
