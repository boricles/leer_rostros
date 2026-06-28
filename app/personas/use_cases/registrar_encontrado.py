"""RegistrarEncontrado use case: RESCATISTA flow."""

from uuid import uuid4

from app.domain.matching import MatchingPolicy
from app.domain.persona import Estado, PersonaBase
from app.domain.privacy import MenoresPrivacy
from app.personas.repositories.persona import PersonaRepository
from app.schemas import AlertaDuplicado, AlertaFamiliar, ResultadoRegistro
from app.shared._exceptions import PersonaValidationError, RostroNoDetectadoError
from app.shared._helpers import ProcessedPhotos, _embedding_consulta, _gen_codigo


class RegistrarEncontrado:
    """RESCATISTA flow: register a found person, alert if a family match exists."""

    def __init__(self, repo: PersonaRepository, policy: MatchingPolicy):
        self._repo = repo
        self._policy = policy

    def execute(
        self,
        *,
        procesadas: ProcessedPhotos,
        es_menor: bool,
        nombre: str | None,
        apellido: str | None,
        doc_tipo: str | None,
        doc_numero: str | None,
        refugio: str | None,
        ubicacion: str | None,
        telefono_responsable: str | None,
        encontrado_por: str | None = None,
        doc_responsable: str | None,
        descripcion: str | None,
        confirmar_duplicado: bool = False,
    ) -> ResultadoRegistro:
        """Register a found person and return registration result with optional alert.

        Validation rules:
        1. At least one photo with a detected face.
        2. refugio is required.
        3. telefono_responsable is required.
        4. If es_menor=True, doc_responsable is required.

        Trazabilidad / duplicados:
        - Si llega `doc_numero` y ya existe un ENCONTRADO con esa cédula:
          * sin `confirmar_duplicado` → NO se crea persona nueva; se devuelve
            `alerta_duplicado` con los datos del registro previo.
          * con `confirmar_duplicado=True` → el avistamiento se agrega al histórico
            de esa persona (timestamp + ubicación) y se actualiza su ubicación actual.
        - Si NO hay duplicado, se crea la persona y se registra su primer evento de
          histórico (el avistamiento inicial).

        Returns:
            ResultadoRegistro with codigo, person_id, optional alerta and alerta_duplicado.

        Raises:
            RostroNoDetectadoError: If no faces detected.
            PersonaValidationError: If required fields are missing.
        """
        # Validation
        if not procesadas:
            raise RostroNoDetectadoError("No se detectó ningún rostro en la(s) foto(s).")
        if not refugio or not refugio.strip():
            raise PersonaValidationError("El refugio actual es obligatorio.")
        if not telefono_responsable or not telefono_responsable.strip():
            raise PersonaValidationError("El teléfono del responsable es obligatorio.")
        if es_menor and not (doc_responsable and doc_responsable.strip()):
            raise PersonaValidationError(
                "Para un menor, la identificación del responsable es obligatoria."
            )

        # Búsqueda INVERSA por cédula: ¿algún familiar ya estaba buscando a esta
        # persona (mismo documento) y no la había encontrado? Se notifica al rescatista.
        familiares = self._alertas_familiares(doc_numero)

        # Trazabilidad: ¿ya existe un encontrado con esta cédula?
        if doc_numero and doc_numero.strip():
            existente = self._repo.find_encontrada_by_doc(doc_numero)
            if existente is not None:
                return self._manejar_duplicado(
                    existente=existente,
                    refugio=refugio,
                    ubicacion=ubicacion,
                    encontrado_por=encontrado_por,
                    telefono_responsable=telefono_responsable,
                    confirmar_duplicado=confirmar_duplicado,
                    coincidencias_familiares=familiares,
                )

        # Build domain object
        person_id = uuid4()
        codigo = _gen_codigo()

        persona = PersonaBase(
            person_id=person_id,
            estado=Estado.ENCONTRADA,
            es_menor=es_menor,
            nombre=nombre,
            apellido=apellido,
            doc_tipo=doc_tipo,
            doc_numero=doc_numero,
            refugio=refugio,
            ubicacion=ubicacion,
            encontrado_por=encontrado_por,
            telefono_responsable=telefono_responsable,
            doc_responsable=doc_responsable,
            descripcion=descripcion,
            moderacion="pendiente",
            codigo=codigo,
        )

        # Persist
        self._repo.add(person_id, persona, procesadas)

        # Trazabilidad: primer evento del histórico (avistamiento inicial).
        self._repo.add_historial(
            str(person_id),
            refugio=refugio,
            ubicacion=ubicacion,
            encontrado_por=encontrado_por,
            telefono_responsable=telefono_responsable,
            nota="registro inicial",
            actualizar_actual=False,  # la persona ya nace con estos datos
        )

        # Cross-flow search for matching buscada
        embedding = _embedding_consulta(procesadas)
        buscados = self._repo.search_by_estado(embedding, "buscada", 1)

        # Build alert if match exists
        alerta = None
        if buscados:
            best = buscados[0]
            d = best["distancia"]
            if self._policy.is_match(d):
                alerta = AlertaFamiliar(
                    person_id=best["person_id"],
                    familiar_nombre=best["nombre"],
                    familiar_telefono=best["telefono"],
                    image_url=best["image_url"],
                    coincidencia=best["coincidencia"],
                    confianza=best["confianza"],
                    es_menor=best["es_menor"],
                )
                alerta = MenoresPrivacy(alerta)

        return ResultadoRegistro(
            codigo=codigo,
            person_id=str(person_id),
            alerta=alerta,
            coincidencias_familiares=familiares,
        )

    def _alertas_familiares(self, doc_numero: str | None) -> list[AlertaFamiliar]:
        """Búsqueda inversa por cédula: familiares que ya buscaban a esta persona.

        Devuelve AlertaFamiliar (coincidencia 100% por documento exacto), con la
        privacidad de menores aplicada. Lista vacía si no hay cédula o nadie buscaba.
        """
        if not (doc_numero and doc_numero.strip()):
            return []
        alertas = []
        for f in self._repo.find_buscadas_by_doc(doc_numero):
            alerta = AlertaFamiliar(
                person_id=f["person_id"],
                familiar_nombre=f.get("nombre"),
                familiar_telefono=f.get("telefono"),
                image_url=f.get("image_url") or "",
                coincidencia=100,
                confianza="alta",
                es_menor=f.get("es_menor", False),
            )
            alertas.append(MenoresPrivacy(alerta))
        return alertas

    def _manejar_duplicado(
        self,
        *,
        existente: dict,
        refugio: str | None,
        ubicacion: str | None,
        encontrado_por: str | None,
        telefono_responsable: str | None,
        confirmar_duplicado: bool,
        coincidencias_familiares: list[AlertaFamiliar] | None = None,
    ) -> ResultadoRegistro:
        """Resuelve el caso de cédula ya existente entre los encontrados."""
        alerta_dup = AlertaDuplicado(
            person_id=existente["person_id"],
            codigo=existente.get("codigo"),
            nombre=existente.get("nombre"),
            apellido=existente.get("apellido"),
            doc_numero=existente.get("doc_numero"),
            refugio=existente.get("refugio"),
            ubicacion=existente.get("ubicacion"),
            image_url=existente.get("image_url"),
            es_menor=existente.get("es_menor", False),
        )
        alerta_dup = MenoresPrivacy(alerta_dup)

        familiares = coincidencias_familiares or []

        if not confirmar_duplicado:
            # Solo avisamos: no creamos duplicado ni tocamos el histórico.
            return ResultadoRegistro(
                codigo=existente.get("codigo") or "",
                person_id=existente["person_id"],
                alerta_duplicado=alerta_dup,
                historial_actualizado=False,
                coincidencias_familiares=familiares,
            )

        # Confirmado: agregamos el avistamiento al histórico de la persona existente
        # y actualizamos su ubicación actual.
        self._repo.add_historial(
            existente["person_id"],
            refugio=refugio,
            ubicacion=ubicacion,
            encontrado_por=encontrado_por,
            telefono_responsable=telefono_responsable,
            nota="avistamiento (duplicado confirmado)",
            actualizar_actual=True,
        )
        return ResultadoRegistro(
            codigo=existente.get("codigo") or "",
            person_id=existente["person_id"],
            alerta_duplicado=alerta_dup,
            historial_actualizado=True,
            coincidencias_familiares=familiares,
        )
