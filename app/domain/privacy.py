"""Menores privacy protocol: mask names at API response boundary."""

from typing import TypeVar

from app.schemas import AlertaFamiliar, Candidato, PersonaAdmin

T = TypeVar("T", Candidato, PersonaAdmin, AlertaFamiliar)


def MenoresPrivacy(obj: T) -> T:
    """Passthrough: ya NO se enmascara el nombre de los menores.

    Decisión de producto (catástrofe / reunificación): para un niño encontrado se
    MUESTRA su nombre/apellido si se conocen (o `null` → el front muestra "Sin nombre
    registrado"). `es_menor` queda solo como etiqueta informativa para la UI.

    Se mantiene la función (y su uso en los endpoints) por compatibilidad; devuelve
    el objeto sin cambios. Si en el futuro se quiere volver a ocultar menores, basta
    con reintroducir el enmascarado aquí.
    """
    return obj
