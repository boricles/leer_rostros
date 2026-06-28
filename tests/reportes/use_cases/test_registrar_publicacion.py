"""Tests for RegistrarPublicacion use case."""

from uuid import uuid4

import pytest

from app.reportes.use_cases import RegistrarPublicacion
from app.schemas import ReportePublicacionIn
from app.shared._exceptions import PersonaNotFoundError, PersonaValidationError
from tests.reportes.repositories.fake import FakeReporteRepository


@pytest.fixture
def fake_repo():
    repo = FakeReporteRepository()
    # Pre-register one persona so we can target it in happy-path tests.
    repo.register_persona(uuid4())
    return repo


@pytest.fixture
def use_case(fake_repo):
    return RegistrarPublicacion(fake_repo)


def _existing_person_id(repo: FakeReporteRepository):
    """Helper: return a UUID that exists in the fake personas registry."""
    return next(iter(repo._personas.keys()))


class TestRegistrarPublicacionHappyPath:
    def test_persists_with_contact(self, use_case, fake_repo):
        """person_id of an existing persona + contact → stored."""
        existing = _existing_person_id(fake_repo)
        datos = ReportePublicacionIn(
            person_id=str(existing),
            descripcion="La foto no corresponde a una persona real",
            contacto="tester@example.com",
        )
        result = use_case.execute(datos)

        assert result["tipo"] == "publicacion"
        assert result["estado"] == "pendiente"
        assert len(fake_repo._reportes) == 1
        stored = fake_repo._reportes[0]
        assert stored["person_id"] == existing
        assert stored["contacto"] == "tester@example.com"
        assert stored["url"] is None  # publicacion reports never carry a URL

    def test_contact_is_optional(self, use_case, fake_repo):
        existing = _existing_person_id(fake_repo)
        datos = ReportePublicacionIn(
            person_id=str(existing),
            descripcion="Contenido ofensivo",
        )
        result = use_case.execute(datos)

        assert result["tipo"] == "publicacion"
        assert fake_repo._reportes[0]["contacto"] is None

    def test_strips_descripcion_whitespace(self, use_case, fake_repo):
        existing = _existing_person_id(fake_repo)
        datos = ReportePublicacionIn(
            person_id=str(existing),
            descripcion="   inapropiado   ",
        )
        use_case.execute(datos)

        assert fake_repo._reportes[0]["descripcion"] == "inapropiado"


class TestRegistrarPublicacionValidation:
    def test_invalid_uuid_raises_validation_error(self, use_case):
        """person_id that is not a UUID → PersonaValidationError (HTTP 422)."""
        datos = ReportePublicacionIn(
            person_id="not-a-uuid",
            descripcion="cualquier cosa",
        )
        with pytest.raises(PersonaValidationError) as exc_info:
            use_case.execute(datos)
        assert "person_id" in str(exc_info.value).lower()

    def test_unknown_persona_raises_not_found(self, use_case, fake_repo):
        """person_id is a valid UUID but no persona matches → PersonaNotFoundError (HTTP 404)."""
        datos = ReportePublicacionIn(
            person_id=str(uuid4()),
            descripcion="inexistente",
        )
        with pytest.raises(PersonaNotFoundError) as exc_info:
            use_case.execute(datos)
        assert "no existe" in str(exc_info.value).lower()

    def test_empty_descripcion_raises_validation(self, use_case, fake_repo):
        existing = _existing_person_id(fake_repo)
        datos = ReportePublicacionIn(
            person_id=str(existing),
            descripcion="    ",
        )
        with pytest.raises(PersonaValidationError):
            use_case.execute(datos)

    def test_does_not_persist_on_validation_error(self, use_case, fake_repo):
        datos = ReportePublicacionIn(
            person_id="not-a-uuid",
            descripcion="cualquier cosa",
        )
        with pytest.raises(PersonaValidationError):
            use_case.execute(datos)
        assert len(fake_repo._reportes) == 0

    def test_does_not_persist_when_persona_missing(self, use_case, fake_repo):
        datos = ReportePublicacionIn(
            person_id=str(uuid4()),
            descripcion="cualquier cosa",
        )
        with pytest.raises(PersonaNotFoundError):
            use_case.execute(datos)
        assert len(fake_repo._reportes) == 0
