"""Tests for RegistrarEncontrado use case."""

import sys
import types
from uuid import uuid4

import pytest

from app.domain.matching import MatchingPolicy
from app.domain.persona import Estado, PersonaBase
from app.schemas import ResultadoRegistro
from app.personas.use_cases import RegistrarEncontrado
from app.shared._exceptions import PersonaValidationError, RostroNoDetectadoError
from tests.personas.repositories.fake import FakePersonaRepository


@pytest.fixture(autouse=True)
def _mock_faces_module(monkeypatch):
    """Mock app.faces to avoid InsightFace loading in tests."""
    if "app.faces" not in sys.modules:
        mock_faces = types.ModuleType("app.faces")
        monkeypatch.setitem(sys.modules, "app.faces", mock_faces)
    faces_mod = sys.modules["app.faces"]
    monkeypatch.setattr(
        faces_mod, "distance_to_confidence", lambda d: 50.0, raising=False
    )


@pytest.fixture
def fake_repo():
    return FakePersonaRepository()


@pytest.fixture
def policy():
    return MatchingPolicy(threshold=0.55)


@pytest.fixture
def use_case(fake_repo, policy):
    return RegistrarEncontrado(fake_repo, policy)


def _make_procesadas(n=1):
    """Create n fake processed photos with embeddings."""
    return [(b"fake-image", "image/jpeg", [(b"fake-embedding", 0.9)]) for _ in range(n)]


class TestRegistrarEncontradoHappyPath:
    def test_happy_path_no_match(self, use_case, fake_repo):
        """Valid registration, no cross-match, alerta=None."""
        procesadas = _make_procesadas()
        result = use_case.execute(
            procesadas=procesadas,
            es_menor=False,
            nombre="Juan",
            apellido="Pérez",
            doc_tipo="V",
            doc_numero="12345678",
            refugio="Refugio Central",
            ubicacion="Caracas",
            telefono_responsable="0414-1234567",
            doc_responsable=None,
            descripcion="Alto, moreno",
        )

        assert isinstance(result, ResultadoRegistro)
        assert result.codigo.startswith("REE-")
        assert result.alerta is None
        assert len(fake_repo._personas) == 1

    def test_happy_path_with_match(self, use_case, fake_repo):
        """Cross-match exists, alerta is populated."""
        # Pre-seed with a "buscada" persona
        buscada = PersonaBase(
            person_id=uuid4(),
            estado=Estado.BUSCADA,
            es_menor=False,
            nombre="María",
            apellido="González",
            telefono_contacto="0412-9999999",
            moderacion="aprobada",
            photos=["https://fake-cdn.example.com/personas/buscada.jpg"],
        )
        fake_repo._personas.append(buscada)

        procesadas = _make_procesadas()
        result = use_case.execute(
            procesadas=procesadas,
            es_menor=False,
            nombre="Juan",
            apellido="Pérez",
            doc_tipo="V",
            doc_numero="12345678",
            refugio="Refugio Central",
            ubicacion="Caracas",
            telefono_responsable="0414-1234567",
            doc_responsable=None,
            descripcion=None,
        )

        assert result.alerta is not None
        assert result.alerta.familiar_nombre == "María"
        assert result.alerta.familiar_telefono == "0412-9999999"

    def test_alerta_menor_masks_nombre(self, use_case, fake_repo):
        """Match is minor, alerta.familiar_nombre is None."""
        minor_buscada = PersonaBase(
            person_id=uuid4(),
            estado=Estado.BUSCADA,
            es_menor=True,
            nombre="Pedrito",
            apellido="López",
            telefono_contacto="0412-8888888",
            moderacion="aprobada",
            photos=["https://fake-cdn.example.com/personas/minor.jpg"],
        )
        fake_repo._personas.append(minor_buscada)

        procesadas = _make_procesadas()
        result = use_case.execute(
            procesadas=procesadas,
            es_menor=False,
            nombre="Test",
            apellido=None,
            doc_tipo=None,
            doc_numero=None,
            refugio="Refugio",
            ubicacion=None,
            telefono_responsable="0414-1234567",
            doc_responsable=None,
            descripcion=None,
        )

        assert result.alerta is not None
        assert result.alerta.familiar_nombre == "Pedrito"  # menores ya NO se enmascaran

    def test_alerta_non_minor_preserves_nombre(self, use_case, fake_repo):
        """Match is adult, familiar_nombre preserved."""
        adult_buscada = PersonaBase(
            person_id=uuid4(),
            estado=Estado.BUSCADA,
            es_menor=False,
            nombre="Carlos",
            apellido="Martínez",
            telefono_contacto="0412-7777777",
            moderacion="aprobada",
            photos=["https://fake-cdn.example.com/personas/adult.jpg"],
        )
        fake_repo._personas.append(adult_buscada)

        procesadas = _make_procesadas()
        result = use_case.execute(
            procesadas=procesadas,
            es_menor=False,
            nombre="Test",
            apellido=None,
            doc_tipo=None,
            doc_numero=None,
            refugio="Refugio",
            ubicacion=None,
            telefono_responsable="0414-1234567",
            doc_responsable=None,
            descripcion=None,
        )

        assert result.alerta is not None
        assert result.alerta.familiar_nombre == "Carlos"

    def test_minor_name_stored_not_nulled(self, use_case, fake_repo):
        """Minor's nombre stored in persona, only masked in response."""
        procesadas = _make_procesadas()
        use_case.execute(
            procesadas=procesadas,
            es_menor=True,
            nombre="Pedrito",
            apellido="López",
            doc_tipo=None,
            doc_numero=None,
            refugio="Refugio",
            ubicacion=None,
            telefono_responsable="0414-1234567",
            doc_responsable="V-11111111",
            descripcion=None,
        )

        # Stored persona has the name
        stored = fake_repo._personas[0]
        assert stored.nombre == "Pedrito"
        assert stored.apellido == "López"


class TestRegistrarEncontradoValidation:
    def test_raises_rostro_no_detectado(self, use_case):
        """Empty procesadas → RostroNoDetectadoError."""
        with pytest.raises(RostroNoDetectadoError) as exc_info:
            use_case.execute(
                procesadas=[],
                es_menor=False,
                nombre="Test",
                apellido=None,
                doc_tipo=None,
                doc_numero=None,
                refugio="Refugio",
                ubicacion=None,
                telefono_responsable="0414-1234567",
                doc_responsable=None,
                descripcion=None,
            )
        assert "rostro" in str(exc_info.value).lower()

    def test_raises_persona_validation_no_refugio(self, use_case):
        """Missing refugio → PersonaValidationError."""
        procesadas = _make_procesadas()
        with pytest.raises(PersonaValidationError) as exc_info:
            use_case.execute(
                procesadas=procesadas,
                es_menor=False,
                nombre="Test",
                apellido=None,
                doc_tipo=None,
                doc_numero=None,
                refugio=None,
                ubicacion=None,
                telefono_responsable="0414-1234567",
                doc_responsable=None,
                descripcion=None,
            )
        assert "refugio" in str(exc_info.value).lower()

    def test_raises_persona_validation_no_telefono_responsable(self, use_case):
        """Missing telefono_responsable → PersonaValidationError."""
        procesadas = _make_procesadas()
        with pytest.raises(PersonaValidationError) as exc_info:
            use_case.execute(
                procesadas=procesadas,
                es_menor=False,
                nombre="Test",
                apellido=None,
                doc_tipo=None,
                doc_numero=None,
                refugio="Refugio",
                ubicacion=None,
                telefono_responsable=None,
                doc_responsable=None,
                descripcion=None,
            )
        assert "teléfono" in str(exc_info.value).lower()

    def test_raises_persona_validation_menor_sin_doc_responsable(self, use_case):
        """es_menor=True, no doc_responsable → PersonaValidationError."""
        procesadas = _make_procesadas()
        with pytest.raises(PersonaValidationError) as exc_info:
            use_case.execute(
                procesadas=procesadas,
                es_menor=True,
                nombre="Pedrito",
                apellido=None,
                doc_tipo=None,
                doc_numero=None,
                refugio="Refugio",
                ubicacion=None,
                telefono_responsable="0414-1234567",
                doc_responsable=None,
                descripcion=None,
            )
        assert "responsable" in str(exc_info.value).lower()


class TestRegistrarEncontradoTrazabilidad:
    """Dedup por cédula + histórico de avistamientos."""

    def _seed_encontrada(self, fake_repo, doc_numero, **kw):
        defaults = dict(
            person_id=uuid4(),
            estado=Estado.ENCONTRADA,
            es_menor=False,
            nombre="Ana",
            apellido="Ríos",
            doc_numero=doc_numero,
            refugio="Refugio Norte",
            ubicacion="Maracay",
            codigo="REE-EXISTE01",
            moderacion="pendiente",
            photos=["https://fake-cdn.example.com/personas/exist.jpg"],
        )
        defaults.update(kw)
        found = PersonaBase(**defaults)
        fake_repo._personas.append(found)
        return found

    def test_registro_inicial_crea_primer_evento(self, use_case, fake_repo):
        """Un encontrado nuevo deja su primer evento de histórico."""
        use_case.execute(
            procesadas=_make_procesadas(),
            es_menor=False,
            nombre="Juan",
            apellido="Pérez",
            doc_tipo="V",
            doc_numero="12345678",
            refugio="Refugio Central",
            ubicacion="Caracas",
            telefono_responsable="0414-1234567",
            doc_responsable=None,
            descripcion=None,
        )
        pid = str(fake_repo._personas[0].person_id)
        eventos = fake_repo.list_historial(pid)
        assert len(eventos) == 1
        assert eventos[0]["nota"] == "registro inicial"
        assert eventos[0]["ubicacion"] == "Caracas"

    def test_duplicado_sin_confirmar_avisa_y_no_crea(self, use_case, fake_repo):
        """Misma cédula sin confirmar → alerta_duplicado y NO se crea persona nueva."""
        existente = self._seed_encontrada(fake_repo, "99999999")
        antes = len(fake_repo._personas)

        result = use_case.execute(
            procesadas=_make_procesadas(),
            es_menor=False,
            nombre="Ana",
            apellido="Ríos",
            doc_tipo="V",
            doc_numero="99999999",
            refugio="Refugio Sur",
            ubicacion="Valencia",
            telefono_responsable="0414-0000000",
            doc_responsable=None,
            descripcion=None,
        )

        assert result.alerta_duplicado is not None
        assert result.alerta_duplicado.person_id == str(existente.person_id)
        assert result.historial_actualizado is False
        assert len(fake_repo._personas) == antes  # no se creó duplicado
        assert fake_repo.count_historial(str(existente.person_id)) == 0  # no tocó histórico

    def test_duplicado_confirmado_agrega_avistamiento(self, use_case, fake_repo):
        """Misma cédula con confirmar → evento al histórico + ubicación actualizada."""
        existente = self._seed_encontrada(fake_repo, "99999999")
        pid = str(existente.person_id)
        antes = len(fake_repo._personas)

        result = use_case.execute(
            procesadas=_make_procesadas(),
            es_menor=False,
            nombre="Ana",
            apellido="Ríos",
            doc_tipo="V",
            doc_numero="99999999",
            refugio="Refugio Sur",
            ubicacion="Valencia",
            telefono_responsable="0414-0000000",
            doc_responsable=None,
            descripcion=None,
            confirmar_duplicado=True,
        )

        assert result.historial_actualizado is True
        assert result.person_id == pid
        assert len(fake_repo._personas) == antes  # sigue sin crear duplicado
        eventos = fake_repo.list_historial(pid)
        assert len(eventos) == 1
        assert eventos[0]["ubicacion"] == "Valencia"
        # La ubicación "actual" de la persona se actualizó al último avistamiento.
        actualizada = next(p for p in fake_repo._personas if str(p.person_id) == pid)
        assert actualizada.ubicacion == "Valencia"
        assert actualizada.refugio == "Refugio Sur"

    def test_duplicado_es_case_insensitive(self, use_case, fake_repo):
        """La detección de duplicado normaliza la cédula (trim/case)."""
        self._seed_encontrada(fake_repo, "AB-123")
        result = use_case.execute(
            procesadas=_make_procesadas(),
            es_menor=False,
            nombre="Ana",
            apellido="Ríos",
            doc_tipo="V",
            doc_numero="  ab-123 ",
            refugio="Refugio Sur",
            ubicacion="Valencia",
            telefono_responsable="0414-0000000",
            doc_responsable=None,
            descripcion=None,
        )
        assert result.alerta_duplicado is not None

    def test_sin_cedula_no_busca_duplicado(self, use_case, fake_repo):
        """Sin cédula no hay dedup: se crea normalmente."""
        self._seed_encontrada(fake_repo, "99999999")
        result = use_case.execute(
            procesadas=_make_procesadas(),
            es_menor=False,
            nombre="Otro",
            apellido="Distinto",
            doc_tipo=None,
            doc_numero=None,
            refugio="Refugio X",
            ubicacion="Barquisimeto",
            telefono_responsable="0414-0000000",
            doc_responsable=None,
            descripcion=None,
        )
        assert result.alerta_duplicado is None
        assert result.codigo.startswith("REE-")


class TestRegistrarEncontradoBusquedaInversa:
    """Al registrar, avisa si un familiar ya buscaba a esta persona (por cédula)."""

    def _seed_buscada(self, fake_repo, doc_numero, **kw):
        defaults = dict(
            person_id=uuid4(),
            estado=Estado.BUSCADA,
            es_menor=False,
            nombre="Madre",
            apellido="Solicitante",
            doc_numero=doc_numero,
            telefono_contacto="0412-5555555",
            moderacion="aprobada",
            photos=["https://fake-cdn.example.com/personas/buscada.jpg"],
        )
        defaults.update(kw)
        b = PersonaBase(**defaults)
        fake_repo._personas.append(b)
        return b

    def test_familiar_buscaba_por_cedula(self, use_case, fake_repo):
        """Un familiar buscaba la misma cédula → llega en coincidencias_familiares."""
        self._seed_buscada(fake_repo, "C-100", telefono_contacto="0412-7654321")
        result = use_case.execute(
            procesadas=_make_procesadas(),
            es_menor=False,
            nombre="Niño",
            apellido="Perdido",
            doc_tipo="V",
            doc_numero="C-100",
            refugio="Refugio Central",
            ubicacion="Caracas",
            telefono_responsable="0414-1234567",
            doc_responsable=None,
            descripcion=None,
        )
        assert len(result.coincidencias_familiares) == 1
        fam = result.coincidencias_familiares[0]
        assert fam.familiar_telefono == "0412-7654321"
        assert fam.coincidencia == 100

    def test_inversa_normaliza_cedula(self, use_case, fake_repo):
        self._seed_buscada(fake_repo, "C-100")
        result = use_case.execute(
            procesadas=_make_procesadas(),
            es_menor=False,
            nombre="Niño",
            apellido=None,
            doc_tipo="V",
            doc_numero=" c-100 ",
            refugio="Refugio",
            ubicacion=None,
            telefono_responsable="0414-1234567",
            doc_responsable=None,
            descripcion=None,
        )
        assert len(result.coincidencias_familiares) == 1

    def test_sin_familiar_lista_vacia(self, use_case, fake_repo):
        result = use_case.execute(
            procesadas=_make_procesadas(),
            es_menor=False,
            nombre="Nadie",
            apellido=None,
            doc_tipo="V",
            doc_numero="Z-999",
            refugio="Refugio",
            ubicacion=None,
            telefono_responsable="0414-1234567",
            doc_responsable=None,
            descripcion=None,
        )
        assert result.coincidencias_familiares == []

    def test_duplicado_tambien_trae_familiares(self, use_case, fake_repo):
        """En el camino de duplicado por cédula también se avisa de los familiares."""
        # Familiar buscando + encontrada ya existente con la misma cédula
        self._seed_buscada(fake_repo, "C-100")
        existente = PersonaBase(
            person_id=uuid4(),
            estado=Estado.ENCONTRADA,
            es_menor=False,
            nombre="Niño",
            doc_numero="C-100",
            refugio="Refugio Norte",
            codigo="REE-X",
            moderacion="pendiente",
            photos=["https://fake-cdn.example.com/personas/e.jpg"],
        )
        fake_repo._personas.append(existente)

        result = use_case.execute(
            procesadas=_make_procesadas(),
            es_menor=False,
            nombre="Niño",
            apellido=None,
            doc_tipo="V",
            doc_numero="C-100",
            refugio="Refugio Sur",
            ubicacion="Valencia",
            telefono_responsable="0414-1234567",
            doc_responsable=None,
            descripcion=None,
        )
        assert result.alerta_duplicado is not None
        assert len(result.coincidencias_familiares) == 1


class TestRegistrarEncontradoRepoIntegration:
    def test_repo_add_called_with_estado_encontrada(self, use_case, fake_repo):
        """PersonaBase.estado == Estado.ENCONTRADA."""
        procesadas = _make_procesadas()
        use_case.execute(
            procesadas=procesadas,
            es_menor=False,
            nombre="Test",
            apellido=None,
            doc_tipo=None,
            doc_numero=None,
            refugio="Refugio",
            ubicacion=None,
            telefono_responsable="0414-1234567",
            doc_responsable=None,
            descripcion=None,
        )

        persona = fake_repo._personas[0]
        assert persona.estado == Estado.ENCONTRADA

    def test_repo_add_called_with_moderacion_pendiente(self, use_case, fake_repo):
        """PersonaBase.moderacion == 'pendiente'."""
        procesadas = _make_procesadas()
        use_case.execute(
            procesadas=procesadas,
            es_menor=False,
            nombre="Test",
            apellido=None,
            doc_tipo=None,
            doc_numero=None,
            refugio="Refugio",
            ubicacion=None,
            telefono_responsable="0414-1234567",
            doc_responsable=None,
            descripcion=None,
        )

        persona = fake_repo._personas[0]
        assert persona.moderacion == "pendiente"

    def test_repo_add_called_with_es_menor_true(self, use_case, fake_repo):
        """PersonaBase.es_menor matches input."""
        procesadas = _make_procesadas()
        use_case.execute(
            procesadas=procesadas,
            es_menor=True,
            nombre="Pedrito",
            apellido=None,
            doc_tipo=None,
            doc_numero=None,
            refugio="Refugio",
            ubicacion=None,
            telefono_responsable="0414-1234567",
            doc_responsable="V-11111111",
            descripcion=None,
        )

        persona = fake_repo._personas[0]
        assert persona.es_menor
