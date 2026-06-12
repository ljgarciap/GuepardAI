"""
test_image_quality_v2.py — Calidad de Selección de Imágenes v2.

Cubre los criterios de aceptación de la spec: dHash perceptual, dedup de
gemelos visuales en ingesta y selección, degradación invertida (IA primero,
pisos duros), aspect ratio con crop seguro y las reglas QA nuevas.

Spec: docs/specs/calidad-seleccion-imagenes-v2.md
Incidente origen: job 27 local (2026-06-12) — slides 12/13 con la misma foto
(gemelos 173/174) y slide 14 pixelada (asset 137, 426px, rechazado y re-admitido
por la degradación), con 0 imágenes IA pese a allow_ai_images=true.
"""
import os
import uuid
import pytest
from unittest.mock import patch

from PIL import Image

import models
from utils.image_hash import compute_dhash, hamming_distance


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de imágenes sintéticas
# ─────────────────────────────────────────────────────────────────────────────
def _gradient_image(path, size=(200, 200), reverse=False):
    """Gradiente horizontal (creciente o decreciente) — estable para dHash."""
    img = Image.new("L", size)
    w = size[0]
    for y in range(size[1]):
        for x in range(w):
            val = (w - 1 - x if reverse else x) * 255 // (w - 1)
            img.putpixel((x, y), val)
    img.save(path)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# dHash (unit, sin BD)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
class TestPerceptualHash:

    def test_same_image_scaled_produces_same_hash(self, tmp_path):
        big = _gradient_image(str(tmp_path / "big.png"), size=(400, 300))
        with Image.open(big) as img:
            img.resize((120, 90), Image.LANCZOS).save(str(tmp_path / "small.png"))

        assert compute_dhash(big) is not None
        assert compute_dhash(big) == compute_dhash(str(tmp_path / "small.png"))

    def test_different_images_produce_different_hashes(self, tmp_path):
        a = _gradient_image(str(tmp_path / "a.png"))
        b = _gradient_image(str(tmp_path / "b.png"), reverse=True)
        assert compute_dhash(a) != compute_dhash(b)

    def test_corrupt_file_returns_none(self, tmp_path):
        bad = tmp_path / "bad.png"
        bad.write_bytes(b"this is not an image")
        assert compute_dhash(str(bad)) is None

    def test_hamming_distance(self):
        assert hamming_distance("00000000000000ff", "00000000000000ff") == 0
        assert hamming_distance("0000000000000000", "0000000000000001") == 1
        assert hamming_distance(None, "ff") is None
        assert hamming_distance("zz", "ff") is None


# ─────────────────────────────────────────────────────────────────────────────
# Expansión de exclusiones por gemelos visuales (integration)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestVisualTwinExclusion:

    def test_expand_includes_twins_and_skips_others(self, db_session, sample_brand):
        from services.assets.asset_library_service import expand_with_visual_twins

        def _asset(p_hash):
            a = models.BrandAsset(
                brand_id=sample_brand.id,
                local_path=f"asset_{uuid.uuid4().hex[:8]}.png",
                category="lifestyle_photos",
                description="twin test asset",
                perceptual_hash=p_hash,
            )
            db_session.add(a)
            return a

        a1 = _asset("aaaa111122223333")
        a2 = _asset("aaaa111122223333")   # gemelo visual de a1
        a3 = _asset("bbbb444455556666")   # foto distinta
        a4 = _asset(None)                  # pre-backfill
        db_session.flush()

        expanded = expand_with_visual_twins(db_session, [a1.id])
        assert a1.id in expanded
        assert a2.id in expanded
        assert a3.id not in expanded

        # Hash null no expande pero tampoco rompe
        expanded_null = expand_with_visual_twins(db_session, [a4.id])
        assert expanded_null == [a4.id]
        assert expand_with_visual_twins(db_session, []) == []


# ─────────────────────────────────────────────────────────────────────────────
# Dedup perceptual en register_asset (integration)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestRegisterAssetTwinDedup:

    def _register(self, db, brand_id, file_path, width=None, height=None):
        from services.assets.asset_library_service import register_asset
        vision_mock = {
            "category": "lifestyle_photos",
            "description": "synthetic gradient",
            "tags": ["test"],
        }
        with patch("services.assets.asset_library_service.run_vision_classification", return_value=vision_mock), \
             patch("providers.llm_provider.get_embedding", return_value=None):
            return register_asset(db, brand_id, file_path, width=width, height=height)

    def test_smaller_variant_reuses_existing_record(self, db_session, sample_brand, tmp_path):
        big = _gradient_image(str(tmp_path / "hero_big.png"), size=(1200, 900))
        with Image.open(big) as img:
            img.resize((300, 225), Image.LANCZOS).save(str(tmp_path / "hero_small.png"))

        first = self._register(db_session, sample_brand.id, big, width=1200, height=900)
        assert first.perceptual_hash is not None

        second = self._register(db_session, sample_brand.id, str(tmp_path / "hero_small.png"))
        assert second.id == first.id  # variante menor → se reutiliza la grande

    def test_bigger_variant_registers_new_record(self, db_session, sample_brand, tmp_path):
        small = _gradient_image(str(tmp_path / "v_small.png"), size=(300, 225))
        with Image.open(small) as img:
            img.resize((1200, 900), Image.LANCZOS).save(str(tmp_path / "v_big.png"))

        first = self._register(db_session, sample_brand.id, small, width=300, height=225)
        second = self._register(db_session, sample_brand.id, str(tmp_path / "v_big.png"), width=1200, height=900)

        assert second.id != first.id  # mejor resolución → registro propio
        assert second.perceptual_hash == first.perceptual_hash  # gemelos para selección/QA


# ─────────────────────────────────────────────────────────────────────────────
# Fixture de pipeline para Art Director y QA (el código abre SessionLocal y
# hace commits internos → datos commiteados + cleanup, patrón test_qa_verdict)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def pipeline_job(create_test_schema):
    from database import SessionLocal
    db = SessionLocal()

    brand = models.Brand(name=f"QualityV2Brand_{os.urandom(3).hex()}")
    db.add(brand); db.commit()

    dna = models.BrandVisualDna(brand_id=brand.id, source_filename="quality_v2.pptx")
    job = models.GenerationJob(
        client_name="pytest_quality_v2", brand_id=brand.id,
        status=models.GenerationJobStatus.PROCESSING, prompt="test",
        allow_ai_images=False,
    )
    prompt_cfg = db.query(models.SystemConfig).filter(
        models.SystemConfig.key == "prompt_art_director_v1").first()
    if not prompt_cfg:
        db.add(models.SystemConfig(
            key="prompt_art_director_v1",
            value="Pick assets: {found_assets} History: {visual_history} Note: {art_direction_note}",
            description="test prompt",
        ))
    threshold_cfg = db.query(models.SystemConfig).filter(
        models.SystemConfig.key == "asset_score_threshold").first()
    if not threshold_cfg:
        db.add(models.SystemConfig(key="asset_score_threshold", value="0.30", description="test"))
    db.add_all([dna, job]); db.commit()

    created = {"brand": brand, "dna": dna, "job": job, "asset_ids": [], "slide_ids": []}

    def add_asset(width, height, tags=None, visual_profile=None, p_hash=None):
        a = models.BrandAsset(
            brand_id=brand.id,
            local_path=f"qv2_{uuid.uuid4().hex[:10]}.png",
            category="lifestyle_photos",
            description=f"test asset {width}x{height}",
            tags=tags or [],
            width=width, height=height,
            visual_profile=visual_profile,
            perceptual_hash=p_hash,
        )
        db.add(a); db.commit()
        created["asset_ids"].append(a.id)
        return a

    def add_slide(number, layout=None, status=models.PresentationSlideStatus.CONTENT_READY,
                  assigned_image=None, content_json=None, planning_json=None):
        s = models.PresentationSlide(
            job_id=job.id, slide_number=number, title=f"Slide {number}",
            layout_slug=layout, status=status,
            assigned_image=assigned_image,
            content_json=content_json or {"visual_tags": ["growth", "strategy", "team"], "bullets": ["a"]},
            planning_json=planning_json,
        )
        db.add(s); db.commit()
        created["slide_ids"].append(s.id)
        return s

    created["add_asset"] = add_asset
    created["add_slide"] = add_slide

    yield db, created

    db.rollback()
    db.query(models.ArtDirectorDecision).filter(models.ArtDirectorDecision.job_id == job.id).delete()
    db.query(models.PresentationSlide).filter(models.PresentationSlide.job_id == job.id).delete()
    db.query(models.GenerationJob).filter(models.GenerationJob.id == job.id).delete()
    if created["asset_ids"]:
        db.query(models.BrandAsset).filter(models.BrandAsset.id.in_(created["asset_ids"])).delete(synchronize_session=False)
    db.query(models.BrandVisualDna).filter(models.BrandVisualDna.id == dna.id).delete()
    db.query(models.Brand).filter(models.Brand.id == brand.id).delete()
    db.commit()
    db.close()


def _run_plan(db, job, strategy, ai_asset=None):
    """Ejecuta plan_presentation_design con la cadena LLM/embeddings mockeada."""
    from services.generation.art_director_service import plan_presentation_design

    patches = [
        patch("services.generation.art_director_service.get_slide_visual_strategy", return_value=strategy),
        patch("providers.llm_provider.get_embedding", return_value=None),
    ]
    ai_mock = patch("services.generation.art_director_service._generate_ai_asset", return_value=ai_asset)

    with patches[0], patches[1], ai_mock as m_ai:
        result = plan_presentation_design(db, job.id)
    db.expire_all()
    return result, m_ai


@pytest.mark.integration
class TestInvertedDegradation:

    def test_ai_generation_fires_before_degradation(self, pipeline_job):
        """Pool estricto vacío + IA autorizada → asset IA, no degradación."""
        db, ctx = pipeline_job
        ctx["job"].allow_ai_images = True
        db.commit()

        # Candidatos por tags (Level 2) pero todos por debajo del mínimo hi-res
        ctx["add_asset"](500, 400, tags=["growth", "strategy", "team"])
        ctx["add_asset"](426, 427, tags=["growth", "strategy", "team"])
        slide = ctx["add_slide"](1)

        ai_asset = ctx["add_asset"](1600, 900, tags=[])
        strategy = {"visual_intent": "Executive", "grammar_type": "split",
                    "suggested_keywords": ["growth"]}
        _run_plan(db, ctx["job"], strategy, ai_asset=ai_asset)

        m_slide = db.query(models.PresentationSlide).get(slide.id)
        assert m_slide.assigned_image == os.path.basename(ai_asset.local_path)
        assert m_slide.planning_json["art_director"]["degraded"] is False

    def test_hi_res_degradation_never_readmits_low_resolution(self, pipeline_job):
        """IA deshabilitada + layout hi-res: rechazados por resolución NO vuelven."""
        db, ctx = pipeline_job

        ctx["add_asset"](1000, 750, tags=["growth", "strategy", "team"])
        ctx["add_asset"](426, 427, tags=["growth", "strategy", "team"])
        slide = ctx["add_slide"](1)

        strategy = {"visual_intent": "Executive", "grammar_type": "split",
                    "suggested_keywords": ["growth"]}
        _run_plan(db, ctx["job"], strategy)

        m_slide = db.query(models.PresentationSlide).get(slide.id)
        # Mejor sin imagen (placeholder) que pixelada: el incidente del job 27
        assert m_slide.assigned_image is None
        assert m_slide.planning_json["art_director"]["degraded"] is False

    def test_non_hi_res_degradation_respects_min_floor(self, pipeline_job):
        """Degradación no hi-res re-admite solo por encima de degraded_min_resolution_px."""
        db, ctx = pipeline_job

        below_floor = ctx["add_asset"](500, 400, tags=["growth", "strategy", "team"])
        above_floor = ctx["add_asset"](700, 500, tags=["growth", "strategy", "team"])
        slide = ctx["add_slide"](1)

        strategy = {"visual_intent": "Executive", "grammar_type": "data_grid",
                    "suggested_keywords": ["growth"]}
        _run_plan(db, ctx["job"], strategy)

        m_slide = db.query(models.PresentationSlide).get(slide.id)
        assert m_slide.assigned_image == os.path.basename(above_floor.local_path)
        assert m_slide.assigned_image != os.path.basename(below_floor.local_path)
        assert m_slide.planning_json["art_director"]["degraded"] is True


@pytest.mark.integration
class TestAspectRatioSafeCrop:

    def test_centered_subject_is_penalized_not_rejected(self, pipeline_job):
        """Hi-res + mismatch: sujeto centrado entra penalizado; sin perfil, fuera."""
        db, ctx = pipeline_job

        # Landscape 16:9 contra el panel vertical de 'split' → mismatch fuerte
        centered = ctx["add_asset"](
            1600, 900, tags=["growth", "strategy", "team"],
            visual_profile={"composition": {"subject_position": "center"}},
        )
        ctx["add_asset"](1600, 900, tags=["growth", "strategy", "team"])  # sin perfil
        slide = ctx["add_slide"](1)

        strategy = {"visual_intent": "Executive", "grammar_type": "split",
                    "suggested_keywords": ["growth"]}
        _run_plan(db, ctx["job"], strategy)

        m_slide = db.query(models.PresentationSlide).get(slide.id)
        assert m_slide.assigned_image == os.path.basename(centered.local_path)
        assert m_slide.planning_json["art_director"]["degraded"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Reglas QA deterministas nuevas (integration)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
class TestValidateBrandNewRules:

    def test_duplicate_image_across_slides_by_perceptual_hash(self, pipeline_job):
        from agents.qa_validator import ValidateBrandTool
        db, ctx = pipeline_job

        twin_a = ctx["add_asset"](1600, 2048, p_hash="cafe000011112222")
        twin_b = ctx["add_asset"](591, 591, p_hash="cafe000011112222")
        ctx["add_slide"](12, layout="data_grid", status=models.PresentationSlideStatus.PLANNED,
                         assigned_image=os.path.basename(twin_a.local_path))
        ctx["add_slide"](13, layout="pillars", status=models.PresentationSlideStatus.PLANNED,
                         assigned_image=os.path.basename(twin_b.local_path))

        result = ValidateBrandTool().run(job_id=ctx["job"].id)

        assert result["status"] == "failed"
        dup = [v for v in result["violations"] if v["rule"] == "DUPLICATE_IMAGE_ACROSS_SLIDES"]
        assert len(dup) == 1
        assert "12" in dup[0]["message"] and "13" in dup[0]["message"]

    def test_low_resolution_image_violation(self, pipeline_job):
        from agents.qa_validator import ValidateBrandTool
        db, ctx = pipeline_job

        tiny = ctx["add_asset"](426, 427, p_hash="dead000011112222")
        ctx["add_slide"](14, layout="split", status=models.PresentationSlideStatus.PLANNED,
                         assigned_image=os.path.basename(tiny.local_path))

        result = ValidateBrandTool().run(job_id=ctx["job"].id)

        assert result["status"] == "failed"
        low = [v for v in result["violations"] if v["rule"] == "LOW_RESOLUTION_IMAGE"]
        assert len(low) == 1
        assert low[0]["slide_number"] == 14
        assert "426px" in low[0]["message"]

    def test_distinct_adequate_images_pass(self, pipeline_job):
        from agents.qa_validator import ValidateBrandTool
        db, ctx = pipeline_job

        a = ctx["add_asset"](1600, 900, p_hash="aaaa000011112222")
        b = ctx["add_asset"](1500, 1000, p_hash="bbbb000011112222")
        ctx["add_slide"](1, layout="split", status=models.PresentationSlideStatus.PLANNED,
                         assigned_image=os.path.basename(a.local_path))
        ctx["add_slide"](2, layout="pillars", status=models.PresentationSlideStatus.PLANNED,
                         assigned_image=os.path.basename(b.local_path))

        result = ValidateBrandTool().run(job_id=ctx["job"].id)
        assert result["status"] == "passed"
        assert result["violations"] == []


@pytest.mark.integration
class TestJudgeVisualContext:

    def test_judge_prompt_includes_assigned_image_data(self, pipeline_job):
        from agents.qa_validator import ScoreFidelityTool
        db, ctx = pipeline_job

        asset = ctx["add_asset"](1600, 900)
        ctx["add_slide"](
            1, layout="split", status=models.PresentationSlideStatus.PLANNED,
            assigned_image=os.path.basename(asset.local_path),
            planning_json={"art_director": {"reasoning": "test", "degraded": True}},
        )

        with patch("providers.llm_provider.generate_json",
                   return_value={"score": 0.9, "needs_rework": False, "reasoning": "ok"}) as m:
            ScoreFidelityTool().run(job_id=ctx["job"].id)

        prompt = m.call_args[0][0]
        assert os.path.basename(asset.local_path) in prompt
        assert "1600" in prompt
        assert '"degraded_asset_quality": true' in prompt
