"""Inserta en Postgres el lote de personas encontradas ya procesado localmente.

Corre EN EL SERVIDOR (tiene acceso a la BD local). Lee records.jsonl (generado por
scripts/embeddings_local.py) e inserta cada persona como ENCONTRADA + su embedding.

- image_url = /fotos/personas/<foto_id>.jpg  (las imágenes se copian a
  LOCAL_STORAGE_DIR/personas/ por separado, vía rsync).
- moderacion = 'aprobada'  (visibles y matcheables de inmediato).
- Idempotente: salta los `codigo` que ya existan en `personas`.

Uso (en el servidor, dentro de /mnt/volumen1/rostros con el venv):
  ./venv/bin/python scripts/insertar_servidor.py --records /ruta/records.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from app.config import get_settings

_INSERT_PERSONA = """
    INSERT INTO personas
      (id, person_id, estado, es_menor, nombre, apellido, edad, doc_numero,
       telefono_responsable, refugio, ubicacion, descripcion, codigo,
       moderacion, image_url, image_key)
    VALUES (%(id)s, %(pid)s, 'encontrada', %(menor)s, %(nombre)s, %(apellido)s, %(edad)s,
            %(cedula)s, %(tel)s, %(refugio)s, %(ubicacion)s, %(descripcion)s, %(codigo)s,
            'aprobada', %(url)s, %(key)s)
"""

_INSERT_EMB = (
    "INSERT INTO persona_embeddings (foto_id, embedding, calidad_rostro) "
    "VALUES (%s, %s, %s)"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    args = ap.parse_args()

    dsn = get_settings().database_url
    insertados = omitidos = 0
    with psycopg.connect(dsn) as conn:
        register_vector(conn)
        # Set de codigos ya existentes para idempotencia (una sola consulta).
        existentes = {
            r[0]
            for r in conn.execute(
                "SELECT codigo FROM personas WHERE codigo IS NOT NULL"
            ).fetchall()
        }
        with open(args.records, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                cod = r["codigo"]
                if cod in existentes:
                    omitidos += 1
                    continue
                foto_id = r["foto_id"]
                person_id = str(uuid.uuid4())
                emb = np.asarray(r["embedding"], dtype=np.float32)
                conn.execute(
                    _INSERT_PERSONA,
                    {
                        "id": foto_id,
                        "pid": person_id,
                        "menor": r.get("es_menor", False),
                        "nombre": r.get("nombre"),
                        "apellido": r.get("apellido"),
                        "edad": r.get("edad"),
                        "cedula": r.get("cedula"),
                        "tel": r.get("telefono"),
                        "refugio": r.get("ubicacion"),
                        "ubicacion": r.get("ubicacion"),
                        "descripcion": (f"Fuente: {r['fuente']}" if r.get("fuente") else None),
                        "codigo": cod,
                        "url": f"/fotos/personas/{foto_id}.jpg",
                        "key": f"personas/{foto_id}.jpg",
                    },
                )
                conn.execute(_INSERT_EMB, (foto_id, emb, r.get("calidad", 1.0)))
                existentes.add(cod)
                insertados += 1
                if insertados % 1000 == 0:
                    conn.commit()
                    print(f"[insert] insertados={insertados} omitidos={omitidos}", flush=True)
        conn.commit()
    print(f"[insert] LISTO insertados={insertados} omitidos={omitidos}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
