"""Tests for RegistrarFalla use case."""

import pytest

from app.reportes.use_cases import RegistrarFalla
from app.schemas import ReporteFallaIn
from app.shared._exceptions import PersonaValidationError
from tests.reportes.repositories.fake import FakeReporteRepository


@pytest.fixture
def fake_repo():
    return FakeReporteRepository()


@pytest.fixture
def use_case(fake_repo):
    return RegistrarFalla(fake_repo)


class TestRegistrarFallaHappyPath:
    def test_persists_with_defaults(self, use_case, fake_repo):
        """descripcion + url + contacto are all stored."""
        datos = ReporteFallaIn(
            descripcion="El botón de login no responde",
            url="https://symtechven.com/login",
            contacto="user@example.com",
        )
        result = use_case.execute(datos)

        assert result["tipo"] == "falla"
        assert result["estado"] == "pendiente"
        assert "id" in result
        assert "created_at" in result
        assert len(fake_repo._reportes) == 1
        stored = fake_repo._reportes[0]
        assert stored["descripcion"] == "El botón de login no responde"
        assert stored["url"] == "https://symtechven.com/login"
        assert stored["contacto"] == "user@example.com"
        assert stored["person_id"] is None

    def test_optional_fields_can_be_none(self, use_case):
        """url and contacto are optional — None is allowed."""
        datos = ReporteFallaIn(descripcion="Algo se rompió en la página")
        result = use_case.execute(datos)

        assert result["tipo"] == "falla"
        assert result["estado"] == "pendiente"

    def test_strips_descripcion_whitespace(self, use_case, fake_repo):
        """Leading/trailing whitespace is trimmed before persisting."""
        datos = ReporteFallaIn(descripcion="   bug en el front   ")
        use_case.execute(datos)

        assert fake_repo._reportes[0]["descripcion"] == "bug en el front"


class TestRegistrarFallaValidation:
    def test_raises_on_empty_descripcion(self, use_case):
        """Whitespace-only descripcion → PersonaValidationError."""
        datos = ReporteFallaIn(descripcion="   ")
        with pytest.raises(PersonaValidationError) as exc_info:
            use_case.execute(datos)
        assert "vacía" in str(exc_info.value).lower()

    def test_does_not_persist_on_validation_error(self, use_case, fake_repo):
        """A failed validation must not leave a partial record in the repo.

        Pydantic enforces min_length=3 on descripcion, so an empty/short
        string raises before reaching the use case. We bypass the schema by
        constructing an instance with a valid length and let the use case
        reject it via the strip-empty check.
        """
        with pytest.raises(PersonaValidationError):
            use_case.execute(ReporteFallaIn(descripcion="   \t   "))
        assert len(fake_repo._reportes) == 0
