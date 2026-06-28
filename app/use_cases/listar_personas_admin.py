"""ListarPersonasAdmin use case: ADMIN list flow."""

from app.domain.privacy import MenoresPrivacy
from app.repositories.persona import PersonaRepository
from app.schemas import PersonaAdmin

LIMITE_MAX_LIST = 500  # cota dura del listado admin


class ListarPersonasAdmin:
    """ADMIN flow: list all registered personas with optional filters."""

    def __init__(self, repo: PersonaRepository):
        self._repo = repo

    def execute(
        self,
        *,
        limite: int,
        estado: str | None,
        moderacion: str | None,
    ) -> list[PersonaAdmin]:
        """List personas for admin view.

        Returns:
            List of PersonaAdmin with privacy masking applied.
        """
        # Clamp: evita LIMIT negativo (500 de Postgres) o sin cota (memoria).
        limite = max(1, min(LIMITE_MAX_LIST, limite))
        results = self._repo.list_admin(limite, estado, moderacion)
        return [MenoresPrivacy(PersonaAdmin(**d)) for d in results]
