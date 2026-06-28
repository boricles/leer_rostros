"""Tests for AgregarHistorial use case."""

from uuid import uuid4

import pytest

from app.domain.persona import Estado, PersonaBase
from app.personas.use_cases import AgregarHistorial
from app.schemas import ResultadoHistorial
from app.shared._exceptions import PersonaNotFoundError, PersonaValidationError
from tests.personas.repositories.fake import FakePersonaRepository


@pytest.fixture
def fake_repo():
    return FakePersonaRepository()


@pytest.fixture
def use_case(fake_repo):
    return AgregarHistorial(fake_repo)


def _seed(fake_repo, **kw):
    defaults = dict(
        person_id=uuid4(),
        estado=Estado.ENCONTRADA,
        es_menor=False,
        nombre="Luis",
        apellido="Mora",
        refugio="Refugio A",
        ubicacion="Caracas",
        moderacion="pendiente",
        photos=["https://fake-cdn.example.com/personas/x.jpg"],
    )
    defaults.update(kw)
    p = PersonaBase(**defaults)
    fake_repo._personas.append(p)
    return p


class TestAgregarHistorial:
    def test_agrega_evento_y_actualiza_ubicacion(self, use_case, fake_repo):
        p = _seed(fake_repo)
        pid = str(p.person_id)

        result = use_case.execute(
            person_id=pid,
            refugio="Refugio B",
            ubicacion="Valencia",
            encontrado_por="José",
            nota="Traslado",
        )

        assert isinstance(result, ResultadoHistorial)
        assert result.total_eventos == 1
        assert result.evento.ubicacion == "Valencia"
        assert result.evento.nota == "Traslado"
        # La ficha refleja el último avistamiento.
        actual = next(x for x in fake_repo._personas if str(x.person_id) == pid)
        assert actual.ubicacion == "Valencia"
        assert actual.refugio == "Refugio B"

    def test_varios_eventos_se_acumulan(self, use_case, fake_repo):
        p = _seed(fake_repo)
        pid = str(p.person_id)
        use_case.execute(person_id=pid, ubicacion="Valencia")
        use_case.execute(person_id=pid, ubicacion="Maracay")
        result = use_case.execute(person_id=pid, ubicacion="Mérida")
        assert result.total_eventos == 3
        assert [e["ubicacion"] for e in fake_repo.list_historial(pid)] == [
            "Valencia",
            "Maracay",
            "Mérida",
        ]

    def test_persona_inexistente_404(self, use_case):
        with pytest.raises(PersonaNotFoundError):
            use_case.execute(person_id=str(uuid4()), ubicacion="Valencia")

    def test_sin_lugar_422(self, use_case, fake_repo):
        p = _seed(fake_repo)
        with pytest.raises(PersonaValidationError) as exc:
            use_case.execute(person_id=str(p.person_id), nota="solo nota")
        assert (
            "refugio" in str(exc.value).lower() or "ubicación" in str(exc.value).lower()
        )

    def test_solo_refugio_es_valido(self, use_case, fake_repo):
        p = _seed(fake_repo)
        result = use_case.execute(person_id=str(p.person_id), refugio="Refugio Z")
        assert result.total_eventos == 1
        assert result.evento.refugio == "Refugio Z"
