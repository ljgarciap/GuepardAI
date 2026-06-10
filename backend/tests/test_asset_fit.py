"""
test_asset_fit.py — Tests unitarios del filtro de aspect ratio (Selección de Imágenes v1).

Funciones puras: no requieren BD ni LLM.
Spec: docs/specs/mejora-seleccion-imagenes.md (criterios 4 y 5).
"""
import pytest

from services.generation.asset_fit import compute_aspect_fit, aspect_penalty_multiplier

# Panel de imagen de strategic_split (brand_composition_dna.GRAMMAR_GEOMETRIES):
# 38% de ancho × 84% de alto sobre un slide 13.33×7.5 in → ratio ≈ 0.804 (vertical)
SPLIT_PANEL = {"left": 55.0, "top": 8.0, "width": 38.0, "height": 84.0, "role": "supporting"}
SLIDE_W, SLIDE_H = 13.33, 7.5


@pytest.mark.unit
class TestComputeAspectFit:

    def test_portrait_image_fits_split_panel(self):
        # 1300×1500 → ratio 0.867 vs panel 0.804 → diff ~0.08, muy por debajo de 0.40
        diff = compute_aspect_fit(1300, 1500, SPLIT_PANEL, SLIDE_W, SLIDE_H)
        assert diff is not None
        assert diff < 0.40

    def test_wide_landscape_image_mismatches_split_panel(self):
        # 1920×1080 → ratio 1.78 vs panel 0.804 → diff ~1.21, fuera de tolerancia
        diff = compute_aspect_fit(1920, 1080, SPLIT_PANEL, SLIDE_W, SLIDE_H)
        assert diff is not None
        assert diff > 0.40

    def test_perfect_fit_returns_zero(self):
        # Imagen con exactamente el ratio del panel
        panel = {"width": 50.0, "height": 50.0}  # ratio = (0.5*13.33)/(0.5*7.5) = 1.777
        diff = compute_aspect_fit(1777, 1000, panel, SLIDE_W, SLIDE_H)
        assert diff == pytest.approx(0.0, abs=0.01)

    def test_missing_dimensions_not_applicable(self):
        # Criterio 5 de la spec: sin dimensiones, el criterio NO aplica (None, no rechazo)
        assert compute_aspect_fit(None, None, SPLIT_PANEL, SLIDE_W, SLIDE_H) is None
        assert compute_aspect_fit(1200, None, SPLIT_PANEL, SLIDE_W, SLIDE_H) is None
        assert compute_aspect_fit(0, 800, SPLIT_PANEL, SLIDE_W, SLIDE_H) is None

    def test_missing_panel_not_applicable(self):
        # Layouts sin geometría de imagen (ej: big_metric) → criterio no aplica
        assert compute_aspect_fit(1920, 1080, None, SLIDE_W, SLIDE_H) is None
        assert compute_aspect_fit(1920, 1080, {}, SLIDE_W, SLIDE_H) is None
        assert compute_aspect_fit(1920, 1080, {"width": 50.0}, SLIDE_W, SLIDE_H) is None

    def test_invalid_slide_dimensions_not_applicable(self):
        assert compute_aspect_fit(1920, 1080, SPLIT_PANEL, 0, 0) is None
        assert compute_aspect_fit(1920, 1080, SPLIT_PANEL, None, None) is None


@pytest.mark.unit
class TestAspectPenaltyMultiplier:

    def test_within_tolerance_no_penalty(self):
        assert aspect_penalty_multiplier(0.10, 0.40) == 1.0
        assert aspect_penalty_multiplier(0.40, 0.40) == 1.0

    def test_not_applicable_no_penalty(self):
        assert aspect_penalty_multiplier(None, 0.40) == 1.0

    def test_beyond_tolerance_penalizes_linearly(self):
        m = aspect_penalty_multiplier(0.60, 0.40)
        assert m == pytest.approx(0.80, abs=0.01)

    def test_penalty_has_floor(self):
        # Nunca expulsa del todo: piso de 0.5
        assert aspect_penalty_multiplier(5.0, 0.40) == 0.5
