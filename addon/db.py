"""Esquema del add-on: tabla `coincidencias`.

Una fila = un par (buscada, encontrada) detectado como match. El UNIQUE evita
duplicar el mismo par y permite que el cron sepa qué ya avisó.

estado_notificacion:
  - 'pendiente'    -> detectado, falta avisar.
  - 'enviada'      -> WhatsApp enviado a la familia.
  - 'fallida'      -> falla transitoria; se reintenta hasta `intentos` < tope.
  - 'sin_telefono' -> el familiar aún no dejó teléfono; se re-evalúa cada corrida.
  - 'omitida'      -> n8n decidió no enviar (bajo umbral); no es error.
  - 'contactado'   -> un admin ya contactó manualmente; el cron no reenvía.
"""

import psycopg

from app.config import get_settings


def init_addon_db() -> None:
    """Crea la tabla `coincidencias` (idempotente). Reusa la misma DB que app."""
    s = get_settings()
    with psycopg.connect(s.database_url, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(927139)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS coincidencias (
                id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                buscada_person_id     UUID NOT NULL,
                encontrada_person_id  UUID NOT NULL,
                distancia             DOUBLE PRECISION NOT NULL,
                coincidencia          INT NOT NULL,
                confianza             TEXT NOT NULL,
                estado_notificacion   TEXT NOT NULL DEFAULT 'pendiente',
                canal                 TEXT,
                wa_to                 TEXT,
                wa_message_id         TEXT,
                error                 TEXT,
                intentos              INT NOT NULL DEFAULT 0,
                created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
                notified_at           TIMESTAMPTZ,
                UNIQUE (buscada_person_id, encontrada_person_id)
            )
            """
        )
        # Idempotente para tablas creadas antes de agregar reintentos.
        conn.execute(
            "ALTER TABLE coincidencias ADD COLUMN IF NOT EXISTS intentos INT NOT NULL DEFAULT 0"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS coincidencias_estado_idx "
            "ON coincidencias (estado_notificacion)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS coincidencias_buscada_idx "
            "ON coincidencias (buscada_person_id)"
        )
        conn.execute("SELECT pg_advisory_unlock(927139)")
