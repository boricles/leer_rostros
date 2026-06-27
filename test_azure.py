"""Prueba de comparación de caras con Azure AI Face.

Uso:
  AZURE_FACE_ENDPOINT=... AZURE_FACE_KEY=... \
  python test_azure.py foto_misma_persona_1.jpg foto_misma_persona_2.jpg foto_otra.jpg

Compara la foto 1 contra la 2 (deberían ser la misma persona → isIdentical=True)
y la foto 1 contra la 3 (distinta persona → isIdentical=False).
"""

import sys

import azure_face as az


def comparar(path_a: str, path_b: str, etiqueta: str) -> None:
    try:
        fa = az.detect_face_id(open(path_a, "rb").read())
        fb = az.detect_face_id(open(path_b, "rb").read())
        res = az.verify(fa, fb)
        print(f"  {etiqueta}: isIdentical={res['isIdentical']}  confidence={res['confidence']:.3f}")
    except Exception as e:
        print(f"  {etiqueta}: ERROR -> {e}")


def main():
    if len(sys.argv) < 3:
        print("Uso: python test_azure.py img1 img2 [img3_distinta]")
        sys.exit(1)
    a, b = sys.argv[1], sys.argv[2]
    print("=== Azure Face — prueba de comparación ===")
    comparar(a, b, "misma persona (1 vs 2)")
    if len(sys.argv) > 3:
        comparar(a, sys.argv[3], "distinta persona (1 vs 3)")


if __name__ == "__main__":
    main()
