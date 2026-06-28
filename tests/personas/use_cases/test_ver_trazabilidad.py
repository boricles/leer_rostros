"""Tests for VerTrazabilidad use case."""

from uuid import uuid4

import pytest

from app.domain.persona import Estado, PersonaBase
from app.personas.use_cases import VerTrazabilidad
from app.schemas import TrazaPersona
from app.shared._exceptions import PersonaNotFoundError
from tests.personas.repositories.fake import FakePersonaRepository


@pytest.fixture
def fake_repo():
    return FakePersonaRepository()


@pytest.fixture
def use_case(fake_repo):
    return VerTrazabilidad(fake_repo)


def _seed(fake_repo):
    p = PersonaBase(
        person_id=uuid4(),
        estado=Estado.ENCONTRADA,
        es_menor=False,
        nombre="Luis",
        refugio="Refugio A",
        moderacion="pendiente",
        photos=["https://fake-cdn.example.com/personas/x.jpg"],
    )
    fake_repo._personas.append(p)
    return p


class TestVerTrazabilidad:
    def test_devuelve_eventos_en_orden(self, use_case, fake_repo):
        p = _seed(fake_repo)
        pid = str(p.person_id)
        fake_repo.add_historial(pid, ubicacion="Caracas", nota="inicial")
        fake_repo.add_historial(pid, ubicacion="Valencia", nota="traslado")

        result = use_case.execute(person_id=pid)

        assert isinstance(result, TrazaPersona)
        assert result.total_eventos == 2
        assert result.eventos[0].ubicacion == "Caracas"
        assert result.eventos[1].ubicacion == "Valencia"

    def test_sin_eventos_devuelve_lista_vacia(self, use_case, fake_repo):
        p = _seed(fake_repo)
        result = use_case.execute(person_id=str(p.person_id))
        assert result.total_eventos == 0
        assert result.eventos == []

    def test_persona_inexistente_404(self, use_case):
        with pytest.raises(PersonaNotFoundError):
            use_case.execute(person_id=str(uuid4()))
