"""
test_analyst_layout_diversity.py — deck-level layout memory for the Analyst
(Synthesis Studio v2, Phase 2).

Hallazgo: con Findings 1/2 (vocabulario) ya resueltos, decks reales seguían
alternando entre solo 2 de los 5 layouts reales (pillars/data_grid ~8 veces
cada uno en 20 slides) — nunca 3 seguidos iguales, así que ninguna regla de
variedad existente lo detectaba. Causa: el Analyst decidía cada slide sin ver
el resto del deck. Este archivo cubre get_recent_layout_history() (la
consulta compartida con el Art Director) y que ambos prompts v4 rendericen
con el placeholder nuevo sin romper el fallback a versiones anteriores.
"""
import pytest

import models
from services.generation.analyst_service import (
    DEFAULT_LAYOUT_DIVERSITY_WINDOW,
    get_layout_diversity_window,
    get_recent_layout_history,
)
from utils.seed import CONFIGS


def _upsert_config(db_session, key, value):
    rec = db_session.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if rec:
        rec.value = value
    else:
        db_session.add(models.SystemConfig(key=key, value=value, description="test"))
    db_session.flush()


def _make_slide(db_session, job_id, slide_number, layout_slug):
    slide = models.PresentationSlide(
        job_id=job_id,
        slide_number=slide_number,
        title=f"Slide {slide_number}",
        content_json={"bullets": []},
        layout_slug=layout_slug,
        status=models.PresentationSlideStatus.CONTENT_READY,
    )
    db_session.add(slide)
    db_session.flush()
    return slide


@pytest.mark.unit
class TestGetLayoutDiversityWindow:

    def test_default_without_config(self, db_session):
        assert get_layout_diversity_window(db_session) == DEFAULT_LAYOUT_DIVERSITY_WINDOW

    def test_reads_seeded_value(self, db_session):
        _upsert_config(db_session, "layout_diversity_window", "9")
        assert get_layout_diversity_window(db_session) == 9

    def test_corrupt_value_falls_back_to_default(self, db_session):
        _upsert_config(db_session, "layout_diversity_window", "not-a-number")
        assert get_layout_diversity_window(db_session) == DEFAULT_LAYOUT_DIVERSITY_WINDOW


@pytest.mark.integration
class TestGetRecentLayoutHistory:

    def test_returns_chronological_order_oldest_first(self, db_session, sample_job):
        _make_slide(db_session, sample_job.id, 1, "hero")
        _make_slide(db_session, sample_job.id, 2, "pillars")
        _make_slide(db_session, sample_job.id, 3, "data_grid")

        history = get_recent_layout_history(db_session, sample_job.id, before_slide_number=4)
        assert history == ["hero", "pillars", "data_grid"]

    def test_respects_the_window_size(self, db_session, sample_job):
        for i in range(1, 6):
            _make_slide(db_session, sample_job.id, i, f"layout_{i}")

        history = get_recent_layout_history(db_session, sample_job.id, before_slide_number=6, window=2)
        assert history == ["layout_4", "layout_5"]

    def test_reveals_a_two_layout_ping_pong(self, db_session, sample_job):
        # El caso real que motivó el fix: alterna sin repetir el inmediato
        # anterior, pero es monótono sobre una ventana más larga.
        pattern = ["pillars", "data_grid", "pillars", "data_grid", "pillars", "data_grid"]
        for i, layout in enumerate(pattern, start=1):
            _make_slide(db_session, sample_job.id, i, layout)

        history = get_recent_layout_history(db_session, sample_job.id, before_slide_number=7)
        assert set(history) == {"pillars", "data_grid"}
        assert len(history) == 6

    def test_slides_without_a_layout_yet_are_excluded(self, db_session, sample_job):
        _make_slide(db_session, sample_job.id, 1, "hero")
        _make_slide(db_session, sample_job.id, 2, None)
        _make_slide(db_session, sample_job.id, 3, "pillars")

        history = get_recent_layout_history(db_session, sample_job.id, before_slide_number=4)
        assert history == ["hero", "pillars"]

    def test_first_slide_of_the_deck_gets_empty_history(self, db_session, sample_job):
        assert get_recent_layout_history(db_session, sample_job.id, before_slide_number=1) == []


@pytest.mark.unit
class TestPromptV4RenderWithRealSeededText:

    def _get_value(self, key):
        matches = [cfg["value"] for cfg in CONFIGS if cfg["key"] == key]
        assert len(matches) == 1
        return matches[0]

    def test_prompt_analyst_v4_renders_with_recent_layouts(self):
        prompt = self._get_value("prompt_analyst_v4").format(
            slide_title="Test slide",
            bullets="['A bullet']",
            rag_context="Some context.",
            recent_layouts='["pillars", "data_grid", "pillars", "data_grid"]',
        )
        assert '"pillars", "data_grid", "pillars", "data_grid"' in prompt
        assert "DIVERSITY RULE" in prompt

    def test_prompt_analyst_v4_renders_with_empty_history_placeholder(self):
        prompt = self._get_value("prompt_analyst_v4").format(
            slide_title="Cover", bullets="[]", rag_context="Ctx.",
            recent_layouts="[] (no previous slide has a layout assigned yet)",
        )
        assert "no previous slide has a layout assigned yet" in prompt

    def test_prompt_art_director_v4_renders_with_visual_history(self):
        prompt = self._get_value("prompt_art_director_v4").format(
            art_direction_note="Clean corporate style.",
            vision_dna_json="{}",
            premium_patterns_json="[]",
            visual_strategy="Executive",
            slide_title="Test",
            bullets="[]",
            found_assets="[]",
            visual_history='["Recent layouts used: [\'pillars\', \'data_grid\', \'pillars\', \'data_grid\']"]',
        )
        assert "pillars" in prompt
        assert "deck-wide" in prompt.lower() or "ping-pong" in prompt.lower()
