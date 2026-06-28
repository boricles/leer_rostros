"""WhatsApp: link wa.me (botón del rescatista) + cliente Evolution API (cron).

- `normalizar_telefono` / `wa_link`: usados por el botón "Contactar" — cero API.
- `EvolutionClient.send_text`: envío automático del cron vía Evolution API.
- `mensaje_familia` / `mensaje_contacto_rescatista`: textos pre-armados.
"""

import re
from urllib.parse import quote

import requests

from addon.config import AddonSettings, get_addon_settings


def normalizar_telefono(raw: str | None, default_country: str = "58") -> str | None:
    """Convierte un teléfono a formato internacional solo-dígitos (sin '+').

    Heurística pragmática (ajústala a tu país):
      - '+58 412-1234567'  -> '584121234567' (ya internacional, se respeta)
      - '00584121234567'   -> '584121234567'
      - '0412-1234567'     -> se quita el 0 local y se antepone el país
      - '4121234567'       -> se antepone el país
    Devuelve None si no quedan dígitos suficientes."""
    if not raw:
        return None
    raw = raw.strip()
    tiene_mas = raw.startswith("+")
    digitos = re.sub(r"\D", "", raw)
    if not digitos:
        return None

    if tiene_mas:
        pass  # ya viene con código de país
    elif digitos.startswith("00"):
        digitos = digitos[2:]
    elif digitos.startswith("0"):
        digitos = default_country + digitos.lstrip("0")
    elif digitos.startswith(default_country) and len(digitos) >= len(default_country) + 8:
        pass  # parece que ya trae el código de país
    else:
        digitos = default_country + digitos

    return digitos if len(digitos) >= 8 else None


def wa_link(telefono: str | None, texto: str, default_country: str = "58") -> str | None:
    """Construye un enlace https://wa.me/<num>?text=... para abrir WhatsApp.

    Devuelve None si el teléfono no se puede normalizar."""
    num = normalizar_telefono(telefono, default_country)
    if not num:
        return None
    return f"https://wa.me/{num}?text={quote(texto)}"


def mensaje_contacto_rescatista(
    *,
    nombre_buscada: str | None,
    refugio: str | None,
    negocio: str = "Reencuentros",
) -> str:
    """Texto que el RESCATISTA envía a la familia al hacer clic en 'Contactar'."""
    quien = nombre_buscada or "la persona que buscas"
    lugar = f" Está en: {refugio}." if refugio else ""
    return (
        f"Hola, te escribo desde {negocio}. "
        f"Creemos haber encontrado a {quien}.{lugar} "
        "¿Podemos coordinar para confirmar la identidad?"
    )


def mensaje_familia(
    *,
    nombre_buscada: str | None,
    refugio: str | None,
    ubicacion: str | None,
    encontrado_por: str | None,
    telefono_responsable: str | None,
    coincidencia: int,
    negocio: str = "Reencuentros",
) -> str:
    """Texto que el CRON envía automáticamente a la familia cuando hay match."""
    quien = nombre_buscada or "la persona que registraste como desaparecida"
    lineas = [
        f"🟢 *{negocio}* — Posible coincidencia ({coincidencia}%)",
        "",
        f"Detectamos un posible reencuentro con {quien}.",
    ]
    if refugio:
        lineas.append(f"📍 Refugio: {refugio}")
    if ubicacion and ubicacion != refugio:
        lineas.append(f"📌 Ubicación: {ubicacion}")
    if encontrado_por:
        lineas.append(f"🙋 Encontrada por: {encontrado_por}")
    if telefono_responsable:
        lineas.append(f"📞 Contacto del refugio: {telefono_responsable}")
    lineas += [
        "",
        "Por favor confirma la identidad lo antes posible. "
        "Este es un aviso automático; puede haber un margen de error.",
    ]
    return "\n".join(lineas)


def build_match_payload(
    m: dict,
    instance_name: str | None = None,
    *,
    default_country: str = "58",
    min_coincidencia: int | None = None,
) -> dict:
    """Arma el payload JSON que espera el webhook n8n `reencuentros-match-notify`.

    `m` es un dict de MatchRepository.pendientes_de_notificar(). El número se
    normaliza UNA sola vez aquí (`telefono`) — n8n debe usar ese campo y NO
    re-normalizar (evita divergencia de código de país)."""
    nombre = " ".join(
        p for p in [m.get("buscada_nombre"), m.get("buscada_apellido")] if p
    ) or None
    payload = {
        "familiar_telefono": m.get("familiar_telefono"),
        "telefono": normalizar_telefono(m.get("familiar_telefono"), default_country),
        "nombre_buscada": nombre,
        "refugio": m.get("refugio"),
        "ubicacion": m.get("ubicacion"),
        "encontrado_por": m.get("encontrado_por"),
        "telefono_responsable": m.get("telefono_responsable"),
        "coincidencia": m.get("coincidencia"),
        "instance_name": instance_name or "",
    }
    if min_coincidencia is not None:
        payload["min_coincidencia"] = min_coincidencia
    return payload


class MessagingError(RuntimeError):
    """Falla al enviar un aviso (Evolution o webhook n8n)."""


# Alias retro-compatible.
EvolutionError = MessagingError


class N8nNotifier:
    """Postea un match al webhook n8n, que se encarga del WhatsApp.

    El webhook responde JSON `{status: 'sent' | 'skipped', ...}`."""

    def __init__(self, url: str, timeout: int = 20):
        self._url = url
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._url)

    def notify_match(self, payload: dict) -> dict:
        if not self.enabled:
            raise MessagingError("MATCH_NOTIFY_WEBHOOK_URL no configurado.")
        try:
            r = requests.post(self._url, json=payload, timeout=self._timeout)
        except requests.RequestException as e:
            raise MessagingError(f"Error de red al llamar n8n: {e}") from None
        if r.status_code >= 400:
            raise MessagingError(f"n8n respondió {r.status_code}: {r.text[:300]}")
        try:
            return r.json()
        except ValueError:
            return {"raw": r.text}


class EvolutionClient:
    """Cliente mínimo para Evolution API (endpoint sendText).

    POST {url}/message/sendText/{instance}
      headers: apikey
      json:    {"number": "<intl>", "text": "<mensaje>"}
    """

    def __init__(self, settings: AddonSettings | None = None):
        self._s = settings or get_addon_settings()

    @property
    def enabled(self) -> bool:
        return self._s.evolution_enabled

    def send_text(self, number: str, text: str) -> dict:
        """Envía un texto. `number` debe venir ya normalizado (solo dígitos).

        Devuelve el JSON de Evolution. Lanza EvolutionError si falla."""
        if not self.enabled:
            raise EvolutionError("Evolution API no está configurada (.env).")
        url = f"{self._s.evolution_url.rstrip('/')}/message/sendText/{self._s.evolution_instance}"
        headers = {"apikey": self._s.evolution_apikey, "Content-Type": "application/json"}
        payload = {"number": number, "text": text}
        try:
            r = requests.post(
                url, json=payload, headers=headers, timeout=self._s.evolution_timeout
            )
        except requests.RequestException as e:
            raise EvolutionError(f"Error de red al llamar Evolution: {e}") from None
        if r.status_code >= 400:
            raise EvolutionError(f"Evolution respondió {r.status_code}: {r.text[:300]}")
        try:
            return r.json()
        except ValueError:
            return {"raw": r.text}

    @staticmethod
    def extract_message_id(resp: dict) -> str | None:
        """Saca el id del mensaje de la respuesta de Evolution (varía por versión)."""
        if not isinstance(resp, dict):
            return None
        key = resp.get("key")
        if isinstance(key, dict) and key.get("id"):
            return str(key["id"])
        return str(resp.get("id")) if resp.get("id") else None

    # ----------------------- conexión de instancia (QR) -----------------------

    def _get(self, path: str, timeout: int | None = None) -> dict:
        if not self.enabled:
            raise MessagingError("Evolution API no está configurada (.env).")
        url = f"{self._s.evolution_url.rstrip('/')}/{path.lstrip('/')}"
        try:
            r = requests.get(
                url, headers={"apikey": self._s.evolution_apikey},
                timeout=timeout or self._s.evolution_timeout,
            )
        except requests.RequestException as e:
            raise MessagingError(f"Error de red al llamar Evolution: {e}") from None
        if r.status_code >= 400:
            raise MessagingError(f"Evolution respondió {r.status_code}: {r.text[:300]}")
        try:
            return r.json()
        except ValueError:
            return {"raw": r.text}

    def connection_state(self, timeout: int | None = None) -> str:
        """GET /instance/connectionState/{instance} → 'open' | 'connecting' | 'close'."""
        resp = self._get(f"instance/connectionState/{self._s.evolution_instance}", timeout)
        inst = resp.get("instance") if isinstance(resp, dict) else None
        if isinstance(inst, dict) and inst.get("state"):
            return str(inst["state"])
        return str(resp.get("state") or "unknown") if isinstance(resp, dict) else "unknown"

    def connect(self, timeout: int | None = None) -> dict:
        """GET /instance/connect/{instance} → QR para escanear.

        Devuelve {base64, code, pairingCode} normalizado (la forma exacta varía por
        versión de Evolution: a veces vienen anidados bajo 'qrcode')."""
        resp = self._get(f"instance/connect/{self._s.evolution_instance}", timeout)
        qr = resp.get("qrcode") if isinstance(resp, dict) else None
        # Guard: si la respuesta no es dict (p.ej. lista), evita AttributeError → 500.
        src = qr if isinstance(qr, dict) else (resp if isinstance(resp, dict) else {})
        return {
            "base64": src.get("base64"),
            "code": src.get("code"),
            "pairingCode": src.get("pairingCode"),
        }
