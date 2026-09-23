"""
test_compose_canvas.py — Artistic Generation Engine v2, Phase 1.
docs/specs/artistic-generation-v2.md

Covers services/generation/canvas_composer_service.py (content_shape
inference, exemplar selection, the compose_canvas_for_job() happy/error
paths) and agents/compose_canvas.py::ComposeCanvasTool's thin wrapper.
generate_premium_json is explicitly patched per test (same pattern as
tests/test_premium_visual_agent_vision_adjust_whitelist.py) — the global
autouse mock_llm_calls fixture only covers generate_json/generate_text.
"""
from unittest.mock import patch

import pytest

import models
from services.generation.canvas_composer_service import (
    _infer_content_shape,
    _select_exemplars,
    _load_brand_colors,
    compose_canvas_for_job,
)
from agents.compose_canvas import ComposeCanvasTool


def _slide(**overrides):
    defaults = dict(slide_number=2, title="Slide", content_json={}, planning_json=None,
                     status=models.PresentationSlideStatus.CONTENT_READY)
    defaults.update(overrides)
    return models.PresentationSlide(**defaults)


def _upsert_config(db_session, key: str, value: str):
    """Upsert, not a blind add(): full-suite runs where an app-boot test (e.g.
    tests/unit/test_footer.py) already ran the real seed_data() and committed
    this key durably would otherwise hit a UniqueViolation (same bug class as
    TestPremiumPatternWhitelistRealign in test_data_alignments.py). db_session's
    rollback-at-teardown reverts either an insert or an in-place update."""
    existing = db_session.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if existing:
        existing.value = value
    else:
        db_session.add(models.SystemConfig(key=key, value=value))
    db_session.flush()


# ---------------------------------------------------------------------------
# _infer_content_shape
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestInferContentShape:

    def test_first_slide_is_cover(self):
        slide = _slide(slide_number=1, content_json={})
        assert _infer_content_shape(slide) == "cover"

    def test_composition_hero_layout_type_is_cover(self):
        slide = _slide(slide_number=3, content_json={"layout_type": "composition_hero"})
        assert _infer_content_shape(slide) == "cover"

    def test_composition_quote_layout_type_is_quote(self):
        slide = _slide(content_json={"layout_type": "composition_quote"})
        assert _infer_content_shape(slide) == "quote"

    def test_two_or_more_metrics_is_metric_comparison(self):
        slide = _slide(content_json={"metrics": [{"label": "A"}, {"label": "B"}]})
        assert _infer_content_shape(slide) == "metric_comparison"

    def test_single_metric_is_not_metric_comparison(self):
        slide = _slide(content_json={"metrics": [{"label": "A"}]})
        assert _infer_content_shape(slide) == "narrative"

    def test_default_is_narrative(self):
        slide = _slide(content_json={"bullets": ["a", "b"]})
        assert _infer_content_shape(slide) == "narrative"


# ---------------------------------------------------------------------------
# _select_exemplars
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSelectExemplars:

    def test_prefers_matching_content_shape(self):
        sigs = [
            {"name": "a", "content_shape": "narrative"},
            {"name": "b", "content_shape": "metric_comparison"},
        ]
        result = _select_exemplars(sigs, "metric_comparison")
        assert result == [{"name": "b", "content_shape": "metric_comparison"}]

    def test_falls_back_to_any_signature_when_no_match(self):
        sigs = [{"name": "a", "content_shape": "narrative"}]
        result = _select_exemplars(sigs, "quote")
        assert result == sigs

    def test_respects_limit(self):
        sigs = [{"name": str(i), "content_shape": "cover"} for i in range(5)]
        assert len(_select_exemplars(sigs, "cover", limit=2)) == 2

    def test_empty_signatures_returns_empty(self):
        assert _select_exemplars([], "cover") == []


# ---------------------------------------------------------------------------
# compose_canvas_for_job
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestComposeCanvasForJob:

    def _seed_prompt(self, db_session):
        _upsert_config(
            db_session, "prompt_compose_canvas_v1",
            "content_shape={content_shape} sigs={mined_signatures} title={slide_title} "
            "content={slide_content} feedback={qa_feedback}",
        )

    def test_raises_when_brand_has_no_mined_grammar(self, db_session, sample_brand, sample_job):
        self._seed_prompt(db_session)
        with pytest.raises(ValueError, match="no mined layout grammar"):
            compose_canvas_for_job(db_session, sample_job.id)

    def test_raises_when_prompt_not_seeded(self, db_session, sample_brand, sample_job):
        # In a full-suite run an earlier app-boot test may have already run the
        # real seed_data() and committed both keys durably — delete both (v2 is
        # tried first, with a fallback to v1) within this session's transaction
        # so they're genuinely absent here; rollback restores them afterward.
        db_session.query(models.SystemConfig).filter(
            models.SystemConfig.key.in_(["prompt_compose_canvas_v1", "prompt_compose_canvas_v2"])
        ).delete(synchronize_session=False)
        db_session.flush()
        with pytest.raises(RuntimeError, match="prompt_compose_canvas_v1"):
            compose_canvas_for_job(db_session, sample_job.id)

    def test_happy_path_writes_canvas_elements_and_decision(self, db_session, sample_brand, sample_job):
        self._seed_prompt(db_session)
        db_session.add(models.BrandLayoutGrammar(
            brand_id=sample_brand.id, source_filename="deck.pdf",
            signatures_json=[{"name": "donut-kpi-trio", "content_shape": "metric_comparison"}],
        ))
        slide = _slide(job_id=sample_job.id, slide_number=1, content_json={"layout_type": "composition_hero"})
        db_session.add(slide)
        db_session.flush()

        fake_response = {
            "content_shape": "cover",
            "canvas_elements": [{"type": "text", "x": 5, "y": 5, "w": 90, "h": 10, "content": "Hi"}],
            "design_reasoning": "Uses the mined ribbon motif.",
        }
        with patch("providers.llm_provider.generate_premium_json", return_value=fake_response) as mock_premium:
            processed = compose_canvas_for_job(db_session, sample_job.id)

        assert processed == 1
        mock_premium.assert_called_once()
        # compose_canvas_for_job() doesn't commit (the caller does, same
        # convention as art_director_service.plan_presentation_design()) — read
        # the in-memory attribute directly, no refresh() needed or correct here.
        assert slide.layout_slug == "custom_canvas"
        assert slide.status == models.PresentationSlideStatus.PLANNED
        assert slide.planning_json["art_director"]["canvas_elements"] == fake_response["canvas_elements"]
        assert slide.planning_json["art_director"]["engine_version"] == "v2_artistic"

        db_session.flush()  # autoflush=False in this test harness — the ArtDirectorDecision add() is pending
        decision = db_session.query(models.ArtDirectorDecision).filter(
            models.ArtDirectorDecision.job_id == sample_job.id,
            models.ArtDirectorDecision.slide_number == 1,
        ).first()
        assert decision is not None
        assert decision.decision_type == "layout_selection"
        assert "v2_artistic" in decision.summary or decision.metadata_json.get("engine_version") == "v2_artistic"

    def test_skips_planned_slides_not_in_qa_feedback(self, db_session, sample_brand, sample_job):
        self._seed_prompt(db_session)
        db_session.add(models.BrandLayoutGrammar(
            brand_id=sample_brand.id, source_filename="deck.pdf",
            signatures_json=[{"name": "x", "content_shape": "narrative"}],
        ))
        slide = _slide(job_id=sample_job.id, slide_number=1, status=models.PresentationSlideStatus.PLANNED)
        db_session.add(slide)
        db_session.flush()

        with patch("providers.llm_provider.generate_premium_json") as mock_premium:
            processed = compose_canvas_for_job(db_session, sample_job.id, qa_feedback={})

        assert processed == 0
        mock_premium.assert_not_called()

    def test_reprocesses_planned_slide_flagged_in_qa_feedback(self, db_session, sample_brand, sample_job):
        self._seed_prompt(db_session)
        db_session.add(models.BrandLayoutGrammar(
            brand_id=sample_brand.id, source_filename="deck.pdf",
            signatures_json=[{"name": "x", "content_shape": "narrative"}],
        ))
        slide = _slide(job_id=sample_job.id, slide_number=1, status=models.PresentationSlideStatus.PLANNED)
        db_session.add(slide)
        db_session.flush()

        fake_response = {"canvas_elements": [], "design_reasoning": "retry"}
        with patch("providers.llm_provider.generate_premium_json", return_value=fake_response) as mock_premium:
            processed = compose_canvas_for_job(db_session, sample_job.id, qa_feedback={1: "too generic"})

        assert processed == 1
        mock_premium.assert_called_once()


# ---------------------------------------------------------------------------
# ComposeCanvasTool (thin wrapper)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestComposeCanvasTool:

    def test_run_delegates_and_returns_count(self, db_session, sample_brand, sample_job):
        _upsert_config(
            db_session, "prompt_compose_canvas_v1",
            "{content_shape}{mined_signatures}{slide_title}{slide_content}{qa_feedback}",
        )
        db_session.add(models.BrandLayoutGrammar(
            brand_id=sample_brand.id, source_filename="d.pdf", signatures_json=[{"name": "x"}],
        ))
        slide = _slide(job_id=sample_job.id, slide_number=1)
        db_session.add(slide)
        db_session.flush()

        tool = ComposeCanvasTool()
        with patch("agents.compose_canvas.SessionLocal", return_value=db_session), \
             patch("providers.llm_provider.generate_premium_json", return_value={"canvas_elements": []}):
            result = tool.run(job_id=sample_job.id)

        assert result == {"status": "success", "slides_processed": 1}


# ---------------------------------------------------------------------------
# _load_brand_colors — real bug: the composer never received actual brand
# colors at all, only mined geometry (which is color-less for text-only
# mined brands too) — it was inventing an unrelated palette every time.
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestLoadBrandColors:

    def test_uses_the_brand_s_real_visual_dna_colors(self, db_session, sample_brand):
        # sample_brand fixture already flushes a BrandVisualDna row — set its
        # colors directly via a fresh query to avoid relying on relationship shape.
        dna = db_session.query(models.BrandVisualDna).filter(
            models.BrandVisualDna.brand_id == sample_brand.id
        ).first()
        dna.primary_color = "#E4022C"
        dna.secondary_color = "#111111"
        db_session.flush()

        colors = _load_brand_colors(db_session, sample_brand.id)
        assert colors["primary"] == "#E4022C"
        assert colors["secondary"] == "#111111"

    def test_falls_back_to_defaults_when_brand_has_no_visual_dna(self, db_session):
        brand = models.Brand(name="NoDnaBrand", about="x", core_value="x")
        db_session.add(brand)
        db_session.flush()

        colors = _load_brand_colors(db_session, brand.id)
        assert colors["primary"] == "#0052A3"
        assert colors["background"] == "#FFFFFF"

    def test_compose_canvas_for_job_includes_brand_colors_in_the_prompt(self, db_session, sample_brand, sample_job):
        _upsert_config(
            db_session, "prompt_compose_canvas_v1",
            "colors={brand_colors} shape={content_shape}",
        )
        dna = db_session.query(models.BrandVisualDna).filter(
            models.BrandVisualDna.brand_id == sample_brand.id
        ).first()
        dna.primary_color = "#ABCDEF"
        db_session.add(models.BrandLayoutGrammar(
            brand_id=sample_brand.id, source_filename="d.pptx", signatures_json=[{"name": "x"}],
        ))
        slide = _slide(job_id=sample_job.id, slide_number=1)
        db_session.add(slide)
        db_session.flush()

        with patch("providers.llm_provider.generate_premium_json", return_value={"canvas_elements": []}) as mock_premium:
            compose_canvas_for_job(db_session, sample_job.id)

        prompt_sent = mock_premium.call_args[0][0]
        assert "#ABCDEF" in prompt_sent
