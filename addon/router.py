"""Router del add-on. Inclúyelo en app.main con:

    from addon.router import router as addon_router
    app.include_router(addon_router)

Endpoints:
  - POST /addon/wa-link              (público) botón "Contactar" del rescatista → link wa.me
  - GET  /addon/matches             (admin)   lista de coincidencias detectadas
  - POST /addon/scan                (admin)   corre el barrido bidireccional ahora (no envía)
  - GET  /addon/contactar/{id}      (admin)   link wa.me a la familia desde el panel
"""

import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_admin
from app.config import get_settings
from app.database import get_pool
from app.domain.matching import MatchingPolicy

from addon.config import get_addon_settings
from addon.db import init_addon_db
from addon.matching_service import scan_matches
from addon.repository import MatchRepository
from addon.whatsapp import EvolutionClient, MessagingError, mensaje_contacto_rescatista, wa_link

router = APIRouter(prefix="/addon", tags=["addon-matching"])

_repo: MatchRepository | None = None
# Cache del último QR de Evolution (TTL) para no re-disparar connect() en cada poll.
_qr_cache: dict = {"data": None, "ts": 0.0}


def get_match_repo() -> MatchRepository:
    """Repositorio del add-on (perezoso). Crea la tabla `coincidencias` la 1ª vez."""
    global _repo
    if _repo is None:
        init_addon_db()
        policy = MatchingPolicy(threshold=get_settings().match_threshold)
        _repo = MatchRepository(get_pool(), policy)
    return _repo


# ----------------------------- schemas -----------------------------


class WaLinkIn(BaseModel):
    telefono: str = Field(..., description="Teléfono del familiar (formato libre).",
                          examples=["0412-1234567"])
    nombre_buscada: str | None = Field(None, examples=["María"])
    refugio: str | None = Field(None, examples=["Refugio Central, Caracas"])


class WaLinkOut(BaseModel):
    telefono_normalizado: str | None
    wa_link: str | None = Field(None, description="https://wa.me/...?text=... o null si el teléfono es inválido.")
    mensaje: str


class MatchOut(BaseModel):
    id: str
    buscada_person_id: str
    encontrada_person_id: str
    distancia: float
    coincidencia: int
    confianza: str
    estado_notificacion: str
    wa_to: str | None = None
    error: str | None = None
    created_at: datetime
    notified_at: datetime | None = None


class ScanOut(BaseModel):
    buscadas_revisadas: int
    matches_nuevos: int
    matches_repetidos: int
    sin_telefono: int


class WaQrOut(BaseModel):
    enabled: bool = Field(..., description="True si Evolution está configurada en el server.")
    instance: str | None = None
    state: str = Field(..., description="'open' (conectado) | 'connecting' | 'close' | 'unknown'.")
    connected: bool = Field(..., description="True si state == 'open'.")
    base64: str | None = Field(None, description="QR como data URL (data:image/png;base64,...). Null si ya está conectado.")
    pairing_code: str | None = Field(None, description="Código de emparejamiento alternativo al QR.")


# ----------------------------- endpoints -----------------------------


@router.post("/wa-link", response_model=WaLinkOut, summary="Botón Contactar (rescatista) → link wa.me")
def crear_wa_link(datos: WaLinkIn):
    """Stateless: arma el link de WhatsApp + mensaje pre-escrito para que el rescatista
    contacte a la familia. No consulta la BD (cero riesgo de enumeración de teléfonos)."""
    a = get_addon_settings()
    msg = mensaje_contacto_rescatista(
        nombre_buscada=datos.nombre_buscada,
        refugio=datos.refugio,
        negocio=a.wa_business_name,
    )
    link = wa_link(datos.telefono, msg, a.wa_default_country)
    from addon.whatsapp import normalizar_telefono

    return WaLinkOut(
        telefono_normalizado=normalizar_telefono(datos.telefono, a.wa_default_country),
        wa_link=link,
        mensaje=msg,
    )


@router.get(
    "/matches",
    response_model=list[MatchOut],
    dependencies=[Depends(get_current_admin)],
    summary="Admin: listar coincidencias detectadas",
)
def listar_matches(limite: int = 100, estado: str | None = None):
    """`estado` = pendiente | enviada | fallida | sin_telefono (vacío = todos)."""
    return get_match_repo().listar(limite=limite, estado=estado)


@router.post(
    "/scan",
    response_model=ScanOut,
    dependencies=[Depends(get_current_admin)],
    summary="Admin: correr el barrido bidireccional ahora (no envía WhatsApp)",
)
def correr_scan(limite: int = 0):
    repo = get_match_repo()
    resumen = scan_matches(repo, repo.policy, limite=limite)
    return ScanOut(
        buscadas_revisadas=resumen.buscadas_revisadas,
        matches_nuevos=resumen.matches_nuevos,
        matches_repetidos=resumen.matches_repetidos,
        sin_telefono=resumen.sin_telefono,
    )


@router.get(
    "/whatsapp/qr",
    response_model=WaQrOut,
    dependencies=[Depends(get_current_admin)],
    summary="Admin: QR para conectar el WhatsApp (Evolution)",
)
def whatsapp_qr():
    """Devuelve el QR de Evolution para escanear desde el celular. Si la instancia ya
    está conectada (`state='open'`), no devuelve QR. El apikey de Evolution NUNCA sale
    del servidor: este endpoint hace de proxy.

    Para no resetear el emparejamiento, `connect()` se cachea `qr_cache_ttl` seg: si el
    panel hace polling, reusa el mismo QR en vez de re-disparar `/instance/connect`."""
    a = get_addon_settings()
    client = EvolutionClient(a)
    if not client.enabled:
        return WaQrOut(enabled=False, instance=None, state="unknown", connected=False)
    t = a.evolution_interactive_timeout
    try:
        state = client.connection_state(timeout=t)
        if state == "open":
            _qr_cache["data"] = None  # invalidar QR viejo
            return WaQrOut(enabled=True, instance=a.evolution_instance, state="open", connected=True)
        # Reusar el QR cacheado si sigue fresco (evita re-disparar connect en cada poll).
        cached = _qr_cache["data"]
        if cached is None or (time.monotonic() - _qr_cache["ts"]) > a.qr_cache_ttl:
            cached = client.connect(timeout=t)
            _qr_cache["data"] = cached
            _qr_cache["ts"] = time.monotonic()
    except MessagingError as e:
        raise HTTPException(502, f"No se pudo hablar con Evolution: {e}") from None
    return WaQrOut(
        enabled=True,
        instance=a.evolution_instance,
        state=state,
        connected=False,
        base64=cached.get("base64"),
        pairing_code=cached.get("pairingCode"),
    )


@router.get(
    "/whatsapp/estado",
    response_model=WaQrOut,
    dependencies=[Depends(get_current_admin)],
    summary="Admin: estado de conexión del WhatsApp (sin pedir QR)",
)
def whatsapp_estado():
    """Solo consulta el estado de conexión (para refrescar sin regenerar el QR)."""
    a = get_addon_settings()
    client = EvolutionClient(a)
    if not client.enabled:
        return WaQrOut(enabled=False, instance=None, state="unknown", connected=False)
    try:
        state = client.connection_state(timeout=a.evolution_interactive_timeout)
    except MessagingError as e:
        raise HTTPException(502, f"No se pudo hablar con Evolution: {e}") from None
    return WaQrOut(
        enabled=True, instance=a.evolution_instance, state=state, connected=(state == "open")
    )


@router.get(
    "/contactar/{buscada_person_id}",
    response_model=WaLinkOut,
    dependencies=[Depends(get_current_admin)],
    summary="Admin: link wa.me a la familia desde el panel",
)
def contactar_familia(buscada_person_id: str, refugio: str | None = None):
    repo = get_match_repo()
    fam = repo.telefono_familiar(buscada_person_id)
    if not fam:
        raise HTTPException(404, "No existe esa persona buscada.")
    a = get_addon_settings()
    msg = mensaje_contacto_rescatista(
        nombre_buscada=fam["nombre"], refugio=refugio, negocio=a.wa_business_name
    )
    from addon.whatsapp import normalizar_telefono

    # Contacto manual del admin → el cron no debe reenviar a esta familia.
    repo.marcar_contactado(buscada_person_id)

    return WaLinkOut(
        telefono_normalizado=normalizar_telefono(fam["telefono"], a.wa_default_country),
        wa_link=wa_link(fam["telefono"], msg, a.wa_default_country),
        mensaje=msg,
    )
