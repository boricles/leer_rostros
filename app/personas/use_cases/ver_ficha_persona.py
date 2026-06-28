"""VerFichaPersona use case: dossier (búsqueda inversa + histórico) de una persona."""

from app.domain.privacy import MenoresPrivacy
from app.personas.repositories.persona import PersonaRepository
from app.schemas import AlertaFamiliar, EventoHistorial, FichaPersona
from app.shared._exceptions import PersonaNotFoundError


class VerFichaPersona:
    """Reúne en un solo lugar la búsqueda INVERSA (quién buscaba a esta persona por
    cédula) y su histórico de avistamientos. Pensado para la vista de admin.
    """

    def __init__(self, repo: PersonaRepository):
        self._repo = repo

    def execute(self, *, person_id: str) -> FichaPersona:
        """Devuelve la ficha de `person_id`.

        Raises:
            PersonaNotFoundError: si el person_id no existe (HTTP 404).
        """
        basics = self._repo.get_persona_basics(person_id)
        if basics is None:
            raise PersonaNotFoundError("No existe esa persona.")

        doc = basics.get("doc_numero")
        familiares = []
        if doc:
            for f in self._repo.find_buscadas_by_doc(doc):
                alerta = AlertaFamiliar(
                    person_id=f["person_id"],
                    familiar_nombre=f.get("nombre"),
                    familiar_telefono=f.get("telefono"),
                    image_url=f.get("image_url") or "",
                    coincidencia=100,
                    confianza="alta",
                    es_menor=f.get("es_menor", False),
                )
                familiares.append(MenoresPrivacy(alerta))

        eventos = [EventoHistorial(**e) for e in self._repo.list_historial(person_id)]
        return FichaPersona(
            person_id=person_id,
            doc_numero=doc,
            familiares_buscando=familiares,
            total_eventos=len(eventos),
            eventos=eventos,
        )
