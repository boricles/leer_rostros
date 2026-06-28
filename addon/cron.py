"""Cron nocturno: detecta matches nuevos y avisa a la familia por WhatsApp.

Uso:
    python -m addon.cron            # barre + envía (si Evolution está configurada)
    python -m addon.cron --dry-run  # barre y registra, pero NO envía

Crontab (todas las noches a las 03:00):
    0 3 * * *  cd /ruta/al/repo && /usr/bin/python -m addon.cron >> /var/log/reencuentros_cron.log 2>&1

Con Docker (servicio aparte que comparte la misma DB), ver addon/README.md.
"""

import sys

from app.config import get_settings
from app.database import get_pool
from app.domain.matching import MatchingPolicy

from addon.config import get_addon_settings
from addon.db import init_addon_db
from addon.matching_service import scan_matches
from addon.repository import MatchRepository
from addon.whatsapp import (
    EvolutionClient,
    N8nNotifier,
    build_match_payload,
    mensaje_familia,
    normalizar_telefono,
)


def _log(msg: str) -> None:
    print(f"[addon.cron] {msg}", flush=True)


def run(dry_run: bool = False) -> int:
    s = get_settings()
    a = get_addon_settings()

    init_addon_db()
    pool = get_pool()
    policy = MatchingPolicy(threshold=s.match_threshold)
    repo = MatchRepository(pool, policy)

    # 1) Detectar y persistir matches nuevos.
    resumen = scan_matches(repo, policy, limite=a.addon_scan_limite)
    _log(
        f"barrido: {resumen.buscadas_revisadas} buscadas | "
        f"{resumen.matches_nuevos} nuevos | {resumen.matches_repetidos} repetidos | "
        f"{resumen.sin_telefono} sin teléfono"
    )

    if dry_run:
        _log("--dry-run: no se envía nada.")
        return 0

    # 2) Enviar avisos pendientes. Preferencia: webhook n8n; fallback: Evolution directo.
    notifier = N8nNotifier(a.match_notify_webhook_url, a.evolution_timeout)
    client = EvolutionClient(a)
    use_n8n = notifier.enabled

    if not use_n8n and not client.enabled:
        _log(
            "Ni MATCH_NOTIFY_WEBHOOK_URL ni Evolution configurados: "
            "matches quedan 'pendiente' sin enviar."
        )
        return 0
    _log("canal de envío: " + ("webhook n8n" if use_n8n else "Evolution directo"))

    # Advisory lock: evita que dos corridas solapadas reenvíen el mismo match.
    with pool.connection() as lock_conn:
        got = lock_conn.execute("SELECT pg_try_advisory_lock(927140)").fetchone()[0]
        if not got:
            _log("otra corrida del cron está activa; salgo sin enviar.")
            return 0
        try:
            return _enviar_pendientes(repo, a, notifier, client, use_n8n)
        finally:
            lock_conn.execute("SELECT pg_advisory_unlock(927140)")


def _enviar_pendientes(repo, a, notifier, client, use_n8n) -> int:
    pendientes = repo.pendientes_de_notificar(max_intentos=a.addon_max_reintentos)
    _log(f"pendientes de avisar: {len(pendientes)}")

    enviados = fallidos = omitidos = sin_tel = 0
    for m in pendientes:
        # Filtro anti-falsos-positivos: solo matches muy probables (>= 80% por defecto).
        if m["coincidencia"] < a.addon_min_coincidencia_aviso:
            omitidos += 1
            continue

        num = normalizar_telefono(m["familiar_telefono"], a.wa_default_country)
        if not num:
            # Sin teléfono aún: NO cuenta como intento; se re-evalúa la próxima corrida.
            repo.marcar(m["id"], estado="sin_telefono")
            sin_tel += 1
            continue

        try:
            if use_n8n:
                payload = build_match_payload(
                    m, a.evolution_instance,
                    default_country=a.wa_default_country,
                    min_coincidencia=a.addon_min_coincidencia_aviso,
                )
                resp = notifier.notify_match(payload)
                status = (resp or {}).get("status", "sent")
                if status == "sent":
                    repo.marcar(m["id"], estado="enviada", wa_to=num, canal="n8n")
                    enviados += 1
                elif status == "skipped":
                    # n8n decidió no enviar (bajo umbral): NO es falla → no reintentar.
                    repo.marcar(m["id"], estado="omitida", wa_to=num, canal="n8n")
                    omitidos += 1
                else:
                    repo.marcar(
                        m["id"], estado="fallida", wa_to=num, canal="n8n",
                        error=f"n8n status={status}", inc_intentos=1,
                    )
                    fallidos += 1
            else:
                texto = mensaje_familia(
                    nombre_buscada=m["buscada_nombre"],
                    refugio=m["refugio"],
                    ubicacion=m["ubicacion"],
                    encontrado_por=m["encontrado_por"],
                    telefono_responsable=m["telefono_responsable"],
                    coincidencia=m["coincidencia"],
                    negocio=a.wa_business_name,
                )
                resp = client.send_text(num, texto)
                repo.marcar(
                    m["id"], estado="enviada", wa_to=num,
                    msg_id=EvolutionClient.extract_message_id(resp),
                )
                enviados += 1
        except Exception as e:  # noqa: BLE001 — falla transitoria: reintentable
            repo.marcar(
                m["id"], estado="fallida", wa_to=num, error=str(e)[:500], inc_intentos=1
            )
            fallidos += 1

    _log(
        f"avisos: {enviados} enviados | {fallidos} fallidos | "
        f"{omitidos} omitidos | {sin_tel} sin teléfono"
    )
    return 0


def main() -> None:
    dry = "--dry-run" in sys.argv
    sys.exit(run(dry_run=dry))


if __name__ == "__main__":
    main()
