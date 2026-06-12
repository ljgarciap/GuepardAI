"""
image_hash.py — Hash perceptual (dHash) puro PIL, sin dependencias nuevas.

Detecta duplicados VISUALES (misma foto a distintas resoluciones/re-encodes),
que el hash exacto de bytes (`file_hash`) no puede ver. Usado por la ingesta
(`register_asset`), la no-repetición de la Fase B del Art Director y la regla
de QA `DUPLICATE_IMAGE_ACROSS_SLIDES`.

Spec: docs/specs/calidad-seleccion-imagenes-v2.md
"""
from typing import Optional

from PIL import Image

# dHash 8x8 de gradientes horizontales → 64 bits → 16 hex chars
_HASH_SIZE = 8


def compute_dhash(image_path: str) -> Optional[str]:
    """
    dHash (difference hash) de 64 bits en hex. Invariante a escala y a
    re-compresión ligera: la misma foto a 591px y a 2048px produce el mismo
    hash. Devuelve None ante cualquier error (imagen corrupta, formato no
    soportado, archivo ausente) — el caller nunca debe abortar por esto.
    """
    try:
        with Image.open(image_path) as img:
            gray = img.convert("L").resize(
                (_HASH_SIZE + 1, _HASH_SIZE), Image.LANCZOS
            )
            pixels = list(gray.getdata())

        bits = 0
        for row in range(_HASH_SIZE):
            for col in range(_HASH_SIZE):
                left = pixels[row * (_HASH_SIZE + 1) + col]
                right = pixels[row * (_HASH_SIZE + 1) + col + 1]
                bits = (bits << 1) | (1 if left > right else 0)
        return f"{bits:016x}"
    except Exception:
        return None


def hamming_distance(hash_a: Optional[str], hash_b: Optional[str]) -> Optional[int]:
    """
    Distancia de Hamming entre dos dHash hex. None si alguno falta o no parsea.
    0 = idénticos; <= 5 suele ser la misma imagen re-escalada.
    """
    if not hash_a or not hash_b:
        return None
    try:
        return bin(int(hash_a, 16) ^ int(hash_b, 16)).count("1")
    except ValueError:
        return None
