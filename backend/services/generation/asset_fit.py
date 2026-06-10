"""
asset_fit.py — Compatibilidad geométrica imagen ↔ panel de layout.

Funciones puras (sin BD, sin LLM) para que el filtro de la Fase B del Art
Director pueda evaluar si una imagen encaja en el panel de imagen del
grammar_type destino sin recortes agresivos.

Spec: docs/specs/mejora-seleccion-imagenes.md
Design: docs/designs/mejora-seleccion-imagenes.md
"""
from typing import Optional


def compute_aspect_fit(
    asset_width: Optional[int],
    asset_height: Optional[int],
    panel_geometry: Optional[dict],
    slide_width: float = 13.33,
    slide_height: float = 7.5,
) -> Optional[float]:
    """
    Calcula la diferencia relativa de aspect ratio entre una imagen y el panel
    de imagen de un layout.

    Args:
        asset_width/asset_height: dimensiones físicas de la imagen en píxeles.
        panel_geometry: dict con 'width' y 'height' en PORCENTAJE del slide
                        (formato de GRAMMAR_GEOMETRIES / get_layout_geometry()["image"]).
        slide_width/slide_height: dimensiones del slide en pulgadas (para
                        convertir los porcentajes del panel a ratio real).

    Returns:
        Diferencia relativa (0.0 = encaje perfecto; 1.0 = el doble/mitad de ancho
        que el panel). None si faltan datos — en ese caso el criterio NO aplica
        y el caller no debe rechazar el asset (criterio 5 de la spec).
    """
    if not asset_width or not asset_height:
        return None
    if not panel_geometry or not isinstance(panel_geometry, dict):
        return None

    panel_w_pct = panel_geometry.get("width")
    panel_h_pct = panel_geometry.get("height")
    if not panel_w_pct or not panel_h_pct:
        return None
    if not slide_width or not slide_height:
        return None

    panel_ratio = (panel_w_pct / 100.0 * slide_width) / (panel_h_pct / 100.0 * slide_height)
    if panel_ratio <= 0:
        return None

    image_ratio = asset_width / asset_height
    return abs(image_ratio - panel_ratio) / panel_ratio


def aspect_penalty_multiplier(aspect_diff: Optional[float], tolerance: float) -> float:
    """
    Multiplicador de penalización de score para layouts NO hi-res: dentro de la
    tolerancia no penaliza (1.0); fuera, decae linealmente hasta un piso de 0.5
    para no expulsar candidatos únicos del pool.
    """
    if aspect_diff is None or aspect_diff <= tolerance:
        return 1.0
    return max(0.5, 1.0 - (aspect_diff - tolerance))
