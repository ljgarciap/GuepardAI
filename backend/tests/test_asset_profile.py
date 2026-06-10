"""
test_asset_profile.py — Tests del perfil visual de assets (Selección de Imágenes v1).

Cubre:
  - Parsing tolerante de AssetVisualProfile (unit).
  - register_asset: persistencia del perfil y fallback ante fallo de Visión (integration).
  - Lectura de asset_score_threshold desde system_configs en la Fase B (integration).

Spec: docs/specs/mejora-seleccion-imagenes.md (criterios 1, 2, 3, 6 y 10).
"""
import os
import pytest
from unittest.mock import patch

from schemas.asset_profile import AssetVisualProfile

VALID_VISION_RESPONSE = {
    "category": "lifestyle_photos",
    "is_person": False,
    "background_type": "complex",
    "description": "Tienda moderna con clientes, sujeto a la izquierda, espacio a la derecha.",
    "tags": ["store", "retail", "people"],
    "orientation": "landscape",
    "dominant_colors": ["#1A73E8", "#FFFFFF"],
    "composition": {"subject_position": "left", "negative_space": ["right", "top"]},
    "layout_suitability": ["hero", "split"],
}


# ─────────────────────────────────────────────────────────────────────────────
# UNIT: Parsing tolerante del perfil
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
class TestAssetVisualProfileParsing:

    def test_valid_full_response(self):
        profile = AssetVisualProfile.from_llm_response(VALID_VISION_RESPONSE)
        assert profile is not None
        assert profile.orientation == "landscape"
        assert profile.dominant_colors == ["#1A73E8", "#FFFFFF"]
        assert profile.composition.subject_position == "left"
        assert profile.composition.negative_space == ["right", "top"]
        assert profile.layout_suitability == ["hero", "split"]

    def test_invalid_fields_discarded_individually(self):
        # Criterio: campos inválidos se descartan campo a campo, no el perfil completo
        res = {
            "orientation": "diagonal",                      # inválido → None
            "dominant_colors": ["#1A73E8", "no-es-hex", 42],  # se filtran los malos
            "composition": {"subject_position": "floating", "negative_space": ["right", "everywhere"]},
            "layout_suitability": ["hero", "trapezoid"],     # se filtra el inválido
        }
        profile = AssetVisualProfile.from_llm_response(res)
        assert profile is not None
        assert profile.orientation is None
        assert profile.dominant_colors == ["#1A73E8"]
        assert profile.composition.subject_position is None
        assert profile.composition.negative_space == ["right"]
        assert profile.layout_suitability == ["hero"]

    def test_colors_normalized_and_capped(self):
        res = {"dominant_colors": ["1a73e8", "#ffffff", "#000000", "#111111", "#222222", "#333333", "#444444"]}
        profile = AssetVisualProfile.from_llm_response(res)
        assert profile.dominant_colors[0] == "#1A73E8"   # se normaliza a #UPPER
        assert len(profile.dominant_colors) == 6          # cap en 6

    def test_lists_as_wrong_types_discarded(self):
        res = {"orientation": "portrait", "dominant_colors": "not-a-list", "layout_suitability": {"hero": True}}
        profile = AssetVisualProfile.from_llm_response(res)
        assert profile is not None
        assert profile.orientation == "portrait"
        assert profile.dominant_colors == []
        assert profile.layout_suitability == []

    def test_empty_or_garbage_returns_none(self):
        assert AssetVisualProfile.from_llm_response({}) is None
        assert AssetVisualProfile.from_llm_response(None) is None
        assert AssetVisualProfile.from_llm_response("texto plano") is None
        assert AssetVisualProfile.from_llm_response({"category": "photos", "tags": ["a"]}) is None

    def test_to_storage_drops_empty_fields(self):
        profile = AssetVisualProfile.from_llm_response({"orientation": "square"})
        data = profile.to_storage()
        assert data == {"orientation": "square"}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de integración
# ─────────────────────────────────────────────────────────────────────────────
def _make_test_image(tmp_path, name="asset.png", size=(100, 80)):
    from PIL import Image
    path = tmp_path / name
    Image.new("RGB", size, color=(30, 100, 200)).save(path)
    return str(path)


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION: register_asset persiste el perfil / fallback ante fallo de Visión
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestRegisterAssetVisualProfile:

    def test_profile_persisted_on_vision_success(self, db_session, sample_brand, tmp_path):
        from services.assets import asset_library_service as lib

        img_path = _make_test_image(tmp_path)
        with patch.object(lib, "generate_vision_json", return_value=VALID_VISION_RESPONSE), \
             patch("providers.llm_provider.get_embedding", return_value=None):
            asset = lib.register_asset(db_session, sample_brand.id, img_path)

        assert asset.visual_profile is not None
        assert asset.visual_profile["orientation"] == "landscape"
        assert asset.visual_profile["composition"]["negative_space"] == ["right", "top"]
        assert asset.visual_profile["layout_suitability"] == ["hero", "split"]
        assert asset.category == "lifestyle_photos"

    def test_vision_failure_registers_asset_without_profile(self, db_session, sample_brand, tmp_path):
        # Criterio 2: fallo de Visión → asset registrado igual, visual_profile=None
        from services.assets import asset_library_service as lib

        img_path = _make_test_image(tmp_path, name="fail.png")
        with patch.object(lib, "generate_vision_json", side_effect=Exception("Vision down")), \
             patch("providers.llm_provider.get_embeddings_batch", return_value=[None], create=True), \
             patch("providers.llm_provider.get_embedding", return_value=None):
            asset = lib.register_asset(db_session, sample_brand.id, img_path)

        assert asset.id is not None
        assert asset.visual_profile is None
        assert asset.category == "photos"  # fallback actual intacto

    def test_malformed_profile_fields_do_not_break_registration(self, db_session, sample_brand, tmp_path):
        from services.assets import asset_library_service as lib

        bad_response = dict(VALID_VISION_RESPONSE)
        bad_response["orientation"] = ["landscape"]      # tipo incorrecto
        bad_response["composition"] = "subject on left"  # tipo incorrecto

        img_path = _make_test_image(tmp_path, name="malformed.png")
        with patch.object(lib, "generate_vision_json", return_value=bad_response), \
             patch("providers.llm_provider.get_embedding", return_value=None):
            asset = lib.register_asset(db_session, sample_brand.id, img_path)

        assert asset.id is not None
        # El perfil conserva lo aprovechable y descarta lo malformado
        assert asset.visual_profile is not None
        assert "orientation" not in asset.visual_profile
        assert asset.visual_profile["layout_suitability"] == ["hero", "split"]


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION: Fase B lee asset_score_threshold desde system_configs (criterio 6)
# y compatibilidad hacia atrás con assets sin perfil (criterio 3)
# ─────────────────────────────────────────────────────────────────────────────
MINIMAL_ART_DIRECTOR_PROMPT = (
    "Strategy: {visual_strategy} | Colors: {primary_color}/{secondary_color} | Font: {primary_font} | "
    "Title: {slide_title} | Bullets: {bullets} | Assets: {found_assets} | History: {visual_history} | "
    "Note: {art_direction_note} | DNA: {vision_dna_json} | Patterns: {premium_patterns_json}"
)


def _upsert_config(db_session, key, value):
    """Idempotente: otros tests de la suite pueden haber commiteado configs vía SessionLocal."""
    import models
    rec = db_session.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if rec:
        rec.value = value
    else:
        db_session.add(models.SystemConfig(key=key, value=value, description="test"))


def _setup_generation_fixtures(db_session, sample_brand, sample_job, threshold_value):
    """Job con un slide CONTENT_READY + asset sin visual_profile + configs mínimas."""
    import models

    _upsert_config(db_session, "asset_score_threshold", str(threshold_value))
    _upsert_config(db_session, "prompt_art_director_v1", MINIMAL_ART_DIRECTOR_PROMPT)
    # El código lee v2 con prioridad; si otro test la commiteó, la anulamos aquí
    _upsert_config(db_session, "prompt_art_director_v2", MINIMAL_ART_DIRECTOR_PROMPT)

    slide = models.PresentationSlide(
        job_id=sample_job.id,
        slide_number=1,
        title="Retail Strategy",
        status=models.PresentationSlideStatus.CONTENT_READY,
        content_json={"visual_tags": ["retail", "store"], "bullets": ["Point A"]},
    )
    db_session.add(slide)

    # Sin visual_profile (compatibilidad hacia atrás) y con ratio compatible con
    # el panel de strategic_split (1300×1500 → diff ~0.08) y resolución hi-res.
    asset = models.BrandAsset(
        brand_id=sample_brand.id,
        file_hash="t" * 64,
        local_path="test_lib_photo.png",
        category="lifestyle_photos",
        description="Foto de tienda para tests",
        tags=["retail", "store"],
        width=1300,
        height=1500,
        is_public=0,
        embedding=None,
    )
    db_session.add(asset)
    db_session.flush()
    return slide, asset


@pytest.mark.integration
class TestThresholdFromConfig:

    def _run_plan(self, db_session, job_id):
        from services.generation.art_director_service import plan_presentation_design
        # Sin embedding disponible → find_best_assets cae al query simple (score 0.5)
        with patch("providers.llm_provider.get_embedding", side_effect=Exception("no embeddings in tests")):
            return plan_presentation_design(db_session, job_id, is_premium=False)

    def test_low_threshold_accepts_library_asset(self, db_session, sample_brand, sample_job):
        import models
        slide, asset = _setup_generation_fixtures(db_session, sample_brand, sample_job, threshold_value=0.30)

        assert self._run_plan(db_session, sample_job.id) is True

        db_session.refresh(slide)
        assert slide.status == models.PresentationSlideStatus.PLANNED
        assert slide.assigned_image == os.path.basename(asset.local_path)
        # El threshold usado queda trazado en planning_json y proviene de la config
        assert slide.planning_json["art_director"]["threshold"] == pytest.approx(0.30)

        audit = db_session.query(models.ArtDirectorDecision).filter(
            models.ArtDirectorDecision.job_id == sample_job.id,
            models.ArtDirectorDecision.decision_type == "layout_selection",
        ).first()
        # Con score 0.5 >= 0.30 el asset NO aparece rechazado por umbral
        rejected_ids = [r.get("id") for r in audit.metadata_json.get("rejected", [])]
        assert asset.id not in rejected_ids

    def test_high_threshold_rejects_in_strict_pass(self, db_session, sample_brand, sample_job):
        import models
        # La cascada Nivel 3 re-puntúa por tags: 0.5 + 2 matches × 0.1 = 0.7.
        # Con threshold 0.75 el asset cae en la pasada estricta del filtro.
        slide, asset = _setup_generation_fixtures(db_session, sample_brand, sample_job, threshold_value=0.75)

        assert self._run_plan(db_session, sample_job.id) is True

        db_session.refresh(slide)
        assert slide.planning_json["art_director"]["threshold"] == pytest.approx(0.75)

        audit = db_session.query(models.ArtDirectorDecision).filter(
            models.ArtDirectorDecision.job_id == sample_job.id,
            models.ArtDirectorDecision.decision_type == "layout_selection",
        ).first()
        # Con score 0.7 < 0.75 el asset SÍ fue rechazado en la pasada estricta
        # (luego la degradación elegante lo recupera — el slide no queda vacío)
        rejected_ids = [r.get("id") for r in audit.metadata_json.get("rejected", [])]
        assert asset.id in rejected_ids
        assert slide.assigned_image == os.path.basename(asset.local_path)
