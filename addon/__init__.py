"""Add-on de matching bidireccional + notificación WhatsApp.

Este paquete vive aparte de `app/` pero REUSA su infraestructura:
  - `app.database.get_pool()`   -> misma conexión Postgres + pgvector
  - `app.config.get_settings()` -> database_url, match_threshold
  - `app.domain.MatchingPolicy` -> mismo umbral / bandas de confianza
  - tablas `personas` / `persona_embeddings` ya pobladas por los flujos existentes

Qué agrega:
  1. Tabla `coincidencias` (addon/db.py) para persistir matches y su estado de aviso.
  2. Barrido bidireccional buscada<->encontrada (addon/matching_service.py).
  3. Botón "Contactar" vía link wa.me para el rescatista (addon/whatsapp.py + router).
  4. Cron nocturno que detecta matches nuevos y avisa por WhatsApp con Evolution API
     (addon/cron.py).
"""
