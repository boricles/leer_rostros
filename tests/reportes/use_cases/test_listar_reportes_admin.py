"""Tests for ListarReportesAdmin use case."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.reportes.use_cases import ListarReportesAdmin
from app.schemas import ReporteAdmin
from tests.reportes.repositories.fake import FakeReporteRepository


@pytest.fixture
def fake_repo():
    return FakeReporteRepository()


@pytest.fixture
def use_case(fake_repo):
    return ListarReportesAdmin(fake_repo)


def _seed_reports(fake_repo: FakeReporteRepository) -> None:
    """Seed two fallas and one publicacion for filtering tests."""
    fake_repo.add_falla(descripcion="bug A", url=None, contacto=None)
    fake_repo.add_falla(descripcion="bug B", url=None, contacto=None)
    fake_repo.add_publicacion(
        descripcion="foto fea",
        person_id=uuid4(),
        contacto=None,
    )


class TestListarReportesAdminHappyPath:
    def test_returns_list_of_reporteadmin(self, use_case, fake_repo):
        _seed_reports(fake_repo)
        result = use_case.execute(tipo=None, estado=None, limite=100)

        assert isinstance(result, list)
        assert len(result) == 3
        assert all(isinstance(r, ReporteAdmin) for r in result)

    def test_empty_repo_returns_empty_list(self, use_case):
        result = use_case.execute(tipo=None, estado=None, limite=100)
        assert result == []

    def test_most_recent_first(self, use_case, fake_repo):
        """Reports are returned in descending order by insertion (newest first)."""
        first = fake_repo.add_falla(descripcion="primero", url=None, contacto=None)
        # Force a different timestamp so ordering is deterministic
        fake_repo._reportes[-1]["created_at"] = datetime.now() - timedelta(hours=2)
        second = fake_repo.add_falla(descripcion="segundo", url=None, contacto=None)
        fake_repo._reportes[-1]["created_at"] = datetime.now() - timedelta(hours=1)
        third = fake_repo.add_falla(descripcion="tercero", url=None, contacto=None)
        fake_repo._reportes[-1]["created_at"] = datetime.now()

        result = use_case.execute(tipo=None, estado=None, limite=100)
        assert [r.descripcion for r in result] == ["tercero", "segundo", "primero"]


class TestListarReportesAdminFilters:
    def test_filter_by_tipo_falla(self, use_case, fake_repo):
        _seed_reports(fake_repo)
        result = use_case.execute(tipo="falla", estado=None, limite=100)

        assert len(result) == 2
        assert all(r.tipo == "falla" for r in result)

    def test_filter_by_tipo_publicacion(self, use_case, fake_repo):
        _seed_reports(fake_repo)
        result = use_case.execute(tipo="publicacion", estado=None, limite=100)

        assert len(result) == 1
        assert result[0].tipo == "publicacion"

    def test_filter_by_estado_pendiente(self, use_case, fake_repo):
        _seed_reports(fake_repo)
        result = use_case.execute(tipo=None, estado="pendiente", limite=100)

        assert len(result) == 3
        assert all(r.estado == "pendiente" for r in result)

    def test_filter_combined(self, use_case, fake_repo):
        _seed_reports(fake_repo)
        result = use_case.execute(tipo="publicacion", estado="pendiente", limite=100)

        assert len(result) == 1
        assert result[0].tipo == "publicacion"
        assert result[0].estado == "pendiente"

    def test_limite_caps_results(self, use_case, fake_repo):
        for _ in range(5):
            fake_repo.add_falla(descripcion="x", url=None, contacto=None)
        result = use_case.execute(tipo=None, estado=None, limite=2)

        assert len(result) == 2

    def test_invalid_tipo_ignored(self, use_case, fake_repo):
        """Unknown tipo values are silently dropped (no filter applied)."""
        _seed_reports(fake_repo)
        result = use_case.execute(tipo="invalid", estado=None, limite=100)
        assert len(result) == 3

    def test_invalid_estado_ignored(self, use_case, fake_repo):
        _seed_reports(fake_repo)
        result = use_case.execute(tipo=None, estado="invalid", limite=100)
        assert len(result) == 3
