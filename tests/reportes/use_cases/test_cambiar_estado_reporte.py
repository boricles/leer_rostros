"""Tests for CambiarEstadoReporte use case."""

from uuid import uuid4

import pytest

from app.reportes.use_cases import CambiarEstadoReporte
from app.shared._exceptions import (
    ModificacionInvalidaError,
    PersonaNotFoundError,
    PersonaValidationError,
)
from tests.reportes.repositories.fake import FakeReporteRepository


@pytest.fixture
def fake_repo():
    return FakeReporteRepository()


@pytest.fixture
def use_case(fake_repo):
    return CambiarEstadoReporte(fake_repo)


def _seed_one(fake_repo: FakeReporteRepository) -> str:
    """Insert a report and return its id (str)."""
    return fake_repo.add_falla(descripcion="test", url=None, contacto=None)["id"]


class TestCambiarEstadoReporteHappyPath:
    @pytest.mark.parametrize(
        "estado", ["pendiente", "revisado", "resuelto", "descartado"]
    )
    def test_each_valid_estado(self, use_case, fake_repo, estado):
        rid = _seed_one(fake_repo)
        result = use_case.execute(reporte_id=rid, valor=estado)

        assert result == {"id": rid, "estado": estado}
        assert fake_repo._reportes[0]["estado"] == estado


class TestCambiarEstadoReporteValidation:
    def test_invalid_valor_raises(self, use_case):
        """valor outside the allowed set → ModificacionInvalidaError (HTTP 400)."""
        rid = "00000000-0000-0000-0000-000000000000"
        with pytest.raises(ModificacionInvalidaError) as exc_info:
            use_case.execute(reporte_id=rid, valor="otro")
        assert "pendiente" in str(exc_info.value)

    def test_invalid_uuid_raises_validation(self, use_case):
        """reporte_id that is not a UUID → PersonaValidationError (HTTP 422)."""
        with pytest.raises(PersonaValidationError) as exc_info:
            use_case.execute(reporte_id="not-a-uuid", valor="revisado")
        assert "reporte_id" in str(exc_info.value).lower()

    def test_unknown_reporte_raises_not_found(self, use_case):
        """Valid UUID but no report matches → PersonaNotFoundError (HTTP 404)."""
        with pytest.raises(PersonaNotFoundError) as exc_info:
            use_case.execute(
                reporte_id="00000000-0000-0000-0000-000000000000",
                valor="revisado",
            )
        assert "no existe" in str(exc_info.value).lower()

    def test_does_not_modify_other_reports(self, use_case, fake_repo):
        """Only the targeted report is updated."""
        rid_a = _seed_one(fake_repo)
        rid_b = _seed_one(fake_repo)

        use_case.execute(reporte_id=rid_a, valor="resuelto")

        assert fake_repo._reportes[0]["estado"] == "resuelto"  # rid_a
        assert fake_repo._reportes[1]["estado"] == "pendiente"  # rid_b unchanged
