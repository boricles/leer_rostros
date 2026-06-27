"""Cliente mínimo de Azure AI Face (REST) para PROBAR la comparación de caras.

Variables de entorno necesarias:
  AZURE_FACE_ENDPOINT=https://trilord243.cognitiveservices.azure.com/
  AZURE_FACE_KEY=<clave de 'Keys and Endpoint' del recurso>

OJO: `returnFaceId` y `verify` son funciones de "acceso limitado" de Azure.
Si la subscripción no está aprobada, la detección NO devuelve faceId (o da 403),
y este test lo dejará claro.
"""

import os

import requests

ENDPOINT = os.environ.get("AZURE_FACE_ENDPOINT", "").rstrip("/")
KEY = os.environ.get("AZURE_FACE_KEY", "")

DETECT_URL = f"{ENDPOINT}/face/v1.0/detect"
VERIFY_URL = f"{ENDPOINT}/face/v1.0/verify"


def detect_face_id(image_bytes: bytes, recognition_model: str = "recognition_04") -> str:
    """Detecta el rostro y devuelve su faceId (temporal, expira en 24 h)."""
    params = {
        "detectionModel": "detection_03",
        "recognitionModel": recognition_model,
        "returnFaceId": "true",
    }
    headers = {"Ocp-Apim-Subscription-Key": KEY, "Content-Type": "application/octet-stream"}
    r = requests.post(DETECT_URL, params=params, headers=headers, data=image_bytes, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"detect {r.status_code}: {r.text}")
    faces = r.json()
    if not faces:
        raise ValueError("No se detectó ningún rostro en la imagen")
    if "faceId" not in faces[0]:
        raise RuntimeError("Azure devolvió el rostro pero SIN faceId → acceso limitado no aprobado")
    return faces[0]["faceId"]


def verify(face_id1: str, face_id2: str) -> dict:
    """Compara dos faceId. Devuelve {'isIdentical': bool, 'confidence': float}."""
    headers = {"Ocp-Apim-Subscription-Key": KEY, "Content-Type": "application/json"}
    r = requests.post(VERIFY_URL, headers=headers, json={"faceId1": face_id1, "faceId2": face_id2}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"verify {r.status_code}: {r.text}")
    return r.json()
