"""Tests for VerFichaPersona use case (búsqueda inversa + histórico)."""

from uuid import uuid4

import pytest

from app.domain.persona import Estado, PersonaBase
from app.personas.use_cases import VerFichaPersona
from app.schemas import FichaPersona
from app.shared._exceptions import PersonaNotFoundError
from tests.personas.repositories.fake import FakePersonaRepository


@pytest.fixture
def fake_repo():
    return FakePersonaRepository()


@pytest.fixture
def use_case(fake_repo):
    return VerFichaPersona(fake_repo)


def _seed_encontrada(fake_repo, doc_numero="C-100"):
    p = PersonaBase(
        person_id=uuid4(),
        estado=Estado.ENCONTRADA,
        es_menor=False,
        nombre="Niño",
        doc_numero=doc_numero,
        refugio="Refugio Norte",
        moderacion="pendiente",
        photos=["https://fake-cdn.example.com/personas/e.jpg"],
    )
    fake_repo._personas.append(p)
    return p


def _seed_buscada(fake_repo, doc_numero="C-100", telefono="0412-7654321"):
    b = PersonaBase(
        person_id=uuid4(),
        estado=Estado.BUSCADA,
        es_menor=False,
        nombre="Madre",
        doc_numero=doc_numero,
        telefono_contacto=telefono,
        moderacion="aprobada",
        photos=["https://fake-cdn.example.com/personas/b.jpg"],
    )
    fake_repo._personas.append(b)
    return b


class TestVerFichaPersona:
    def test_ficha_combina_familiares_e_historial(self, use_case, fake_repo):
        enc = _seed_encontrada(fake_repo, "C-100")
        _seed_buscada(fake_repo, "C-100", telefono="0412-0001122")
        pid = str(enc.person_id)
        fake_repo.add_historial(pid, ubicacion="Caracas", nota="registro inicial")
        fake_repo.add_historial(pid, ubicacion="Valencia", nota="traslado")

        result = use_case.execute(person_id=pid)

        assert isinstance(result, FichaPersona)
        assert result.doc_numero == "C-100"
        assert len(result.familiares_buscando) == 1
        assert result.familiares_buscando[0].familiar_telefono == "0412-0001122"
        assert result.total_eventos == 2
        assert [e.ubicacion for e in result.eventos] == ["Caracas", "Valencia"]

    def test_sin_familiares_ni_eventos(self, use_case, fake_repo):
        enc = _seed_encontrada(fake_repo, "Z-999")
        result = use_case.execute(person_id=str(enc.person_id))
        assert result.familiares_buscando == []
        assert result.total_eventos == 0

    def test_sin_cedula_no_busca_familiares(self, use_case, fake_repo):
        enc = _seed_encontrada(fake_repo, doc_numero=None)
        _seed_buscada(fake_repo, "C-100")
        result = use_case.execute(person_id=str(enc.person_id))
        assert result.familiares_buscando == []

    def test_persona_inexistente_404(self, use_case):
        with pytest.raises(PersonaNotFoundError):
            use_case.execute(person_id=str(uuid4()))
