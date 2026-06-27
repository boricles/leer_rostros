"""Benchmark del modelo de rescue-vnzla (dlib / face-api.js) sobre LFW.

Usa face_recognition (mismo modelo ResNet-34 de dlib que usa face-api.js).
No requiere TensorFlow. Compara contra los números de Facenet512 del servidor.
"""

import os

import numpy as np
import face_recognition
from sklearn.datasets import fetch_lfw_pairs
from sklearn.metrics import roc_auc_score

N = int(os.environ.get("N_PAIRS", "200"))


def to_uint8(img):
    a = np.asarray(img)
    if a.max() <= 1.0:
        a = a * 255
    return np.ascontiguousarray(a.astype(np.uint8))


def main():
    print("Descargando/cargando LFW pairs...")
    lfw = fetch_lfw_pairs(subset="test", color=True, resize=1.0, funneled=True)
    pairs, labels = lfw.pairs, lfw.target
    same = [i for i in range(len(labels)) if labels[i] == 1][: N // 2]
    diff = [i for i in range(len(labels)) if labels[i] == 0][: N // 2]
    idx = same + diff
    print(f"{len(idx)} pares ({len(same)} misma, {len(diff)} distinta)")

    dists, labs, fails = [], [], 0
    for k, i in enumerate(idx):
        try:
            e1 = face_recognition.face_encodings(to_uint8(pairs[i][0]))
            e2 = face_recognition.face_encodings(to_uint8(pairs[i][1]))
            if not e1 or not e2:
                fails += 1
                continue
            d = float(np.linalg.norm(e1[0] - e2[0]))
            dists.append(d)
            labs.append(int(labels[i]))
        except Exception:
            fails += 1
        if (k + 1) % 40 == 0:
            print(f"  {k + 1}/{len(idx)}...")

    dists, labs = np.array(dists), np.array(labs)
    acc06 = np.mean((dists < 0.6) == (labs == 1))
    best_t, best_acc = 0.0, 0.0
    for t in np.unique(dists):
        acc = np.mean((dists < t) == (labs == 1))
        if acc > best_acc:
            best_acc, best_t = acc, float(t)
    auc = roc_auc_score(labs, -dists)

    print("\n=== dlib / face-api.js (rescue-vnzla) en LFW ===")
    print(f"  n={len(labs)} pares válidos (fallos detección: {fails})")
    print(f"  accuracy @ umbral 0.6 (default) = {acc06 * 100:.1f}%")
    print(f"  accuracy óptima = {best_acc * 100:.1f}% (umbral {best_t:.3f})")
    print(f"  AUC = {auc:.3f}")


if __name__ == "__main__":
    main()
