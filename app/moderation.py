"""Moderación de contenido de las imágenes subidas.

Dos detectores, ambos ONNX (sobre el mismo `onnxruntime` que ya usa InsightFace —
SIN PyTorch, para no inflar la RAM del servidor):

- **NSFW (desnudez)** → NudeNet. Si detecta desnudez explícita, la subida se
  RECHAZA y no se guarda nada.
- **Contenido sensible (gore/violencia/armas)** → CLIP zero-shot. NO borra la
  publicación: solo la marca con un flag para que el front la difumine y el
  superadmin la revise.

Diseño DEFENSIVO (fail-open): si un modelo no carga o falla en una imagen, la
moderación NO bloquea la subida. En una catástrofe la prioridad es que el servicio
nunca deje de funcionar; un modelo caído no debe tumbar la app. Los fallos se loguean.
"""

from __future__ import annotations

import io
import threading
from dataclasses import dataclass, field

import numpy as np

from app.config import get_settings

# --------------------------------------------------------------------------- #
# Resultado de moderar una imagen
# --------------------------------------------------------------------------- #


@dataclass
class Veredicto:
    """Resultado de moderar una imagen."""

    nsfw: bool = False  # desnudez explícita -> rechazar la subida
    sensible: bool = False  # gore/violencia -> marcar flag (no borrar)
    nsfw_score: float = 0.0
    sensible_score: float = 0.0
    etiquetas: list[str] = field(default_factory=list)  # categorías sensibles detectadas


# --------------------------------------------------------------------------- #
# NSFW — NudeNet (detección de desnudez)
# --------------------------------------------------------------------------- #

_nude_detector = None
_nude_lock = threading.Lock()
_nude_failed = False  # si la carga falló, no reintentar en cada request

# Clases de NudeNet que consideramos desnudez EXPLÍCITA (motivo de rechazo).
# Deliberadamente NO incluimos clases "tapadas" (..._COVERED) ni pies/torso.
_NSFW_CLASSES = {
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "FEMALE_BREAST_EXPOSED",
    "ANUS_EXPOSED",
    "BUTTOCKS_EXPOSED",
}


def _get_nude_detector():
    """Carga perezosa del detector NudeNet (singleton). Devuelve None si falla."""
    global _nude_detector, _nude_failed
    if _nude_detector is not None or _nude_failed:
        return _nude_detector
    with _nude_lock:
        if _nude_detector is None and not _nude_failed:
            try:
                from nudenet import NudeDetector

                _nude_detector = NudeDetector()
            except Exception as e:  # pragma: no cover - depende del entorno
                _nude_failed = True
                print(f"[moderation] NudeNet no disponible: {e}", flush=True)
    return _nude_detector


def _detectar_nsfw(data: bytes, umbral: float) -> tuple[bool, float, list[str]]:
    """Devuelve (es_nsfw, score_max, clases). Fail-open: ante error, (False, 0, [])."""
    detector = _get_nude_detector()
    if detector is None or not data:
        return (False, 0.0, [])

    try:
        import cv2

        arr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:  # buffer vacío / formato no soportado / archivo corrupto
            return (False, 0.0, [])
        # NudeNet 3.x acepta un ndarray BGR (mismo formato que cv2.imdecode).
        detecciones = detector.detect(img)
    except Exception as e:  # pragma: no cover - defensivo
        print(f"[moderation] fallo al detectar NSFW: {e}", flush=True)
        return (False, 0.0, [])

    score_max = 0.0
    clases: list[str] = []
    for d in detecciones or []:
        clase = d.get("class") or d.get("label") or ""
        score = float(d.get("score", 0.0))
        if clase in _NSFW_CLASSES and score >= umbral:
            clases.append(clase)
            score_max = max(score_max, score)
    return (bool(clases), score_max, clases)


# --------------------------------------------------------------------------- #
# Gore / violencia — CLIP zero-shot
# --------------------------------------------------------------------------- #

_clip = None  # dict: {session, processor, in_names, sens_idx}
_clip_lock = threading.Lock()
_clip_failed = False

# Etiquetas de referencia. CLIP zero-shot hace softmax sobre TODAS: por eso incluimos
# descripciones "neutrales" que compiten con las "sensibles". Las sensibles son las que
# nos interesan agregar.
_CLIP_LABELS = [
    "a normal everyday photo of a person",  # 0  neutral
    "a photo of a human face",              # 1  neutral
    "a regular photo of people or a place", # 2  neutral
    "a graphic photo with blood and gore",  # 3  sensible
    "a photo of a severe wound or injury",  # 4  sensible
    "a photo of a dead body or a corpse",   # 5  sensible
    "a photo showing physical violence",    # 6  sensible
    "a photo of a weapon such as a gun or knife",  # 7  sensible
]
_CLIP_SENSITIVE_IDX = (3, 4, 5, 6, 7)

# Repo de pesos ONNX (transformers.js) y processor de referencia de OpenAI.
_CLIP_ONNX_REPO = "Xenova/clip-vit-base-patch32"
_CLIP_ONNX_FILE = "onnx/model_quantized.onnx"  # cuantizado: ~1/4 de RAM, suficiente
_CLIP_PROCESSOR = "openai/clip-vit-base-patch32"


def _get_clip():
    """Carga perezosa de CLIP (processor + sesión ONNX). Devuelve None si falla."""
    global _clip, _clip_failed
    if _clip is not None or _clip_failed:
        return _clip
    with _clip_lock:
        if _clip is None and not _clip_failed:
            try:
                import onnxruntime as ort
                from huggingface_hub import hf_hub_download
                from transformers import CLIPProcessor

                processor = CLIPProcessor.from_pretrained(_CLIP_PROCESSOR)
                model_path = hf_hub_download(
                    repo_id=_CLIP_ONNX_REPO, filename=_CLIP_ONNX_FILE
                )
                session = ort.InferenceSession(
                    model_path, providers=["CPUExecutionProvider"]
                )
                in_names = {i.name for i in session.get_inputs()}
                _clip = {
                    "session": session,
                    "processor": processor,
                    "in_names": in_names,
                }
            except Exception as e:  # pragma: no cover - depende del entorno
                _clip_failed = True
                print(f"[moderation] CLIP no disponible: {e}", flush=True)
    return _clip


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / e.sum()


def _detectar_sensible(data: bytes, umbral: float) -> tuple[bool, float, list[str]]:
    """Devuelve (es_sensible, prob_agregada, etiquetas). Fail-open ante error."""
    clip = _get_clip()
    if clip is None:
        return (False, 0.0, [])

    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("RGB")
        inputs = clip["processor"](
            text=_CLIP_LABELS, images=img, return_tensors="np", padding=True
        )
        feed = {}
        if "pixel_values" in clip["in_names"]:
            feed["pixel_values"] = inputs["pixel_values"].astype(np.float32)
        if "input_ids" in clip["in_names"]:
            feed["input_ids"] = inputs["input_ids"].astype(np.int64)
        if "attention_mask" in clip["in_names"]:
            feed["attention_mask"] = inputs["attention_mask"].astype(np.int64)

        out_names = [o.name for o in clip["session"].get_outputs()]
        outputs = clip["session"].run(None, feed)
        res = dict(zip(out_names, outputs))

        if "logits_per_image" in res:
            logits = np.asarray(res["logits_per_image"]).reshape(-1)
        else:
            # Fallback: calcular logits desde los embeddings normalizados.
            img_emb = np.asarray(res.get("image_embeds"))
            txt_emb = np.asarray(res.get("text_embeds"))
            img_emb = img_emb / np.linalg.norm(img_emb, axis=-1, keepdims=True)
            txt_emb = txt_emb / np.linalg.norm(txt_emb, axis=-1, keepdims=True)
            logits = (img_emb @ txt_emb.T).reshape(-1) * 100.0

        probs = _softmax(logits)
        prob_sensible = float(sum(probs[i] for i in _CLIP_SENSITIVE_IDX))
        etiquetas = [
            _CLIP_LABELS[i]
            for i in _CLIP_SENSITIVE_IDX
            if probs[i] >= 0.15  # solo listar las categorías con peso real
        ]
        return (prob_sensible >= umbral, prob_sensible, etiquetas)
    except Exception as e:  # pragma: no cover - defensivo
        print(f"[moderation] fallo al detectar contenido sensible: {e}", flush=True)
        return (False, 0.0, [])


# --------------------------------------------------------------------------- #
# API pública del módulo
# --------------------------------------------------------------------------- #


def moderar(data: bytes) -> Veredicto:
    """Modera una imagen. Si la moderación está deshabilitada, devuelve veredicto limpio.

    NSFW (desnudez explícita) -> nsfw=True  (la subida debe rechazarse).
    Gore/violencia            -> sensible=True (marcar flag, NO borrar).
    """
    s = get_settings()
    if not s.moderation_enabled or not data:
        return Veredicto()

    # Defensa total: si CUALQUIER cosa falla, la moderación no bloquea la subida.
    try:
        nsfw, nsfw_score, nsfw_clases = _detectar_nsfw(data, s.nsfw_threshold)
    except Exception as e:  # pragma: no cover - defensivo
        print(f"[moderation] NSFW error inesperado: {e}", flush=True)
        nsfw, nsfw_score, nsfw_clases = (False, 0.0, [])
    if nsfw:
        # Si ya es NSFW se rechaza; no hace falta correr el de gore.
        return Veredicto(
            nsfw=True, nsfw_score=nsfw_score, etiquetas=nsfw_clases
        )

    try:
        sensible, sens_score, etiquetas = _detectar_sensible(data, s.gore_threshold)
    except Exception as e:  # pragma: no cover - defensivo
        print(f"[moderation] gore error inesperado: {e}", flush=True)
        sensible, sens_score, etiquetas = (False, 0.0, [])
    return Veredicto(
        nsfw=False,
        sensible=sensible,
        nsfw_score=nsfw_score,
        sensible_score=sens_score,
        etiquetas=etiquetas,
    )


def warmup() -> None:
    """Pre-carga los modelos de moderación para evitar el cold start en la 1ª subida."""
    s = get_settings()
    if not s.moderation_enabled:
        return
    _get_nude_detector()
    _get_clip()
