"""Reportes use cases — one class per business flow."""

from app.reportes.use_cases.cambiar_estado_reporte import CambiarEstadoReporte
from app.reportes.use_cases.listar_reportes_admin import ListarReportesAdmin
from app.reportes.use_cases.registrar_falla import RegistrarFalla
from app.reportes.use_cases.registrar_publicacion import RegistrarPublicacion

__all__ = [
    "CambiarEstadoReporte",
    "ListarReportesAdmin",
    "RegistrarFalla",
    "RegistrarPublicacion",
]
