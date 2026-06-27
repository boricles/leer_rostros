"""Benchmark a escala de modelos de reconocimiento facial sobre el dataset LFW.

Descarga pares etiquetados (misma / distinta persona) de LFW y compara cada
modelo de DeepFace por accuracy y AUC. Usa detector='skip' (LFW ya viene
alineado) para que sea rápido — esto compara la calidad del MODELO.

Uso:
   N_PAIRS=300 python benchmark_lfw.py
"""

import os

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import cv2
import numpy as np
from sklearn.datasets import fetch_lfw_pairs
from sklearn.metrics import roc_auc_score
from deepface import DeepFace

N = int(os.environ.get("N_PAIRS", "300"))
MODELS = os.environ.get("MODELS", "SFace,Facenet,Facenet512,ArcFace,VGG-Face").split(",")
DETECTOR = os.environ.get("FACE_DETECTOR", "skip")  # 'retinaface' = config real de producción
ALIGN = os.environ.get("ALIGN", "0") == "1"


def to_uint8(img):
    a = np.asarray(img)
    if a.max() <= 1.0:
        a = a * 255
    a = a.astype(np.uint8)
    return cv2.cvtColor(a, cv2.COLOR_RGB2BGR)  # LFW viene en RGB, DeepFace espera BGR


def cosine(a, b):
    return float(1 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def emb(model, img):
    r = DeepFace.represent(
        img_path=img, model_name=model,
        detector_backend=DETECTOR, enforce_detection=False, align=ALIGN,
    )
    return np.array(r[0]["embedding"], dtype=np.float32)


def main():
    print("Descargando LFW pairs (subset test)...")
    lfw = fetch_lfw_pairs(subset="test", color=True, resize=1.0, funneled=True)
    pairs, labels = lfw.pairs, lfw.target  # label 1 = misma persona

    # Muestra balanceada: mitad 'misma', mitad 'distinta'
    same = [i for i in range(len(labels)) if labels[i] == 1][: N // 2]
    diff = [i for i in range(len(labels)) if labels[i] == 0][: N // 2]
    idx = same + diff
    print(f"{len(idx)} pares ({len(same)} misma, {len(diff)} distinta)\n")

    results = []
    for model in MODELS:
        dists, labs = [], []
        for i in idx:
            try:
                e1 = emb(model, to_uint8(pairs[i][0]))
                e2 = emb(model, to_uint8(pairs[i][1]))
                dists.append(cosine(e1, e2))
                labs.append(int(labels[i]))
            except Exception:
                pass
        dists, labs = np.array(dists), np.array(labs)
        if len(labs) < 4:
            print(f"{model}: sin datos suficientes")
            continue
        best_t, best_acc = 0.0, 0.0
        for t in np.unique(dists):
            acc = np.mean((dists < t) == (labs == 1))
            if acc > best_acc:
                best_acc, best_t = acc, float(t)
        auc = roc_auc_score(labs, -dists)
        results.append((model, best_acc, auc, best_t))
        print(f"{model:11} accuracy={best_acc*100:5.1f}%  AUC={auc:.3f}  umbral_opt={best_t:.3f}  (n={len(labs)})")

    print("\n=== RANKING en LFW (mayor accuracy = mejor) ===")
    for m, acc, auc, t in sorted(results, key=lambda r: -r[1]):
        print(f"  {m:11} accuracy={acc*100:5.1f}%  AUC={auc:.3f}  umbral_opt={t:.3f}")


if __name__ == "__main__":
    main()
