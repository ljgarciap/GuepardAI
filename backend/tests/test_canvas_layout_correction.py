"""
test_canvas_layout_correction.py — Artistic Generation Engine v2.
docs/specs/artistic-generation-v2.md

Covers services/generation/canvas_layout_correction.py: the deterministic
fix for a defect the QA judge could only detect, not repair — a live
2-retry test still left 4/17 real slides with a title wrapping into the
body text below it. auto_correct_overlaps() expands text elements to their
real estimated height and pushes down whatever was stacked below them in
the same horizontal column, applied BEFORE render, not after the fact.
"""
import pytest

from services.generation.canvas_layout_correction import (
    auto_correct_overlaps,
    estimate_text_height_pct,
)
from agents.qa_validator import _summarize_canvas_elements


@pytest.mark.unit
class TestEstimateTextHeightPct:

    def test_longer_text_estimates_more_height(self):
        short = estimate_text_height_pct("Short", 24, 50)
        long = estimate_text_height_pct("A much longer piece of text that will wrap across several lines", 24, 50)
        assert long > short

    def test_missing_inputs_return_zero(self):
        assert estimate_text_height_pct("", 24, 50) == 0.0
        assert estimate_text_height_pct("text", 0, 50) == 0.0
        assert estimate_text_height_pct("text", 24, 0) == 0.0


@pytest.mark.unit
class TestAutoCorrectOverlaps:

    def test_non_list_input_returned_unchanged(self):
        assert auto_correct_overlaps(None) is None
        assert auto_correct_overlaps("not a list") == "not a list"

    def test_does_not_mutate_the_input_list(self):
        original = [{"type": "text", "x": 0, "y": 0, "w": 50, "h": 1, "size": 44, "content": "A very long wrapping title here"}]
        auto_correct_overlaps(original)
        assert original[0]["h"] == 1  # untouched

    def test_non_text_elements_never_modified(self):
        elements = [{"type": "shape", "x": 0, "y": 0, "w": 100, "h": 5, "shape": "rect"}]
        corrected = auto_correct_overlaps(elements)
        assert corrected[0] == elements[0]

    def test_real_defect_from_job_41_slide_4_gets_fixed(self):
        # Exact geometry from the real generated slide that shipped this
        # defect: "CLIENTE" (7 chars, size 48, w=13.83%) wraps mid-word and
        # overlaps the title below it.
        elements = [
            {"type": "text", "x": 4.1, "y": 11.83, "w": 13.83, "h": 13.34, "size": 48, "content": "CLIENTE"},
            {"type": "text", "x": 4.1, "y": 28, "w": 50, "h": 10, "size": 32, "content": "Relevancia en Cada Punto de Contacto"},
        ]
        assert _summarize_canvas_elements(elements)["overlapping_text_pairs"] == 1  # confirms the defect first

        corrected = auto_correct_overlaps(elements)
        assert _summarize_canvas_elements(corrected)["overlapping_text_pairs"] == 0

    def test_short_text_in_unrelated_column_untouched(self):
        # Two columns (x-ranges don't overlap) — correcting the left column's
        # title must never move anything in the right column.
        elements = [
            {"type": "text", "x": 4, "y": 10, "w": 30, "h": 5, "size": 44, "content": "A long title that will wrap across two full lines here"},
            {"type": "text", "x": 65, "y": 12, "w": 20, "h": 5, "size": 18, "content": "Side note"},
        ]
        corrected = auto_correct_overlaps(elements)
        assert corrected[1]["y"] == 12
        assert corrected[1]["h"] == 5

    def test_third_element_in_same_column_cascades_correctly(self):
        # A pushes B down, and B pushing down must also push C if B now
        # collides with C — not just a single pairwise fix.
        elements = [
            {"type": "text", "x": 0, "y": 0, "w": 20, "h": 2, "size": 40, "content": "A title long enough to wrap across two lines"},
            {"type": "text", "x": 0, "y": 5, "w": 20, "h": 2, "size": 40, "content": "Another wrapping line of text right after"},
            {"type": "text", "x": 0, "y": 10, "w": 20, "h": 3, "size": 14, "content": "Footer note"},
        ]
        corrected = auto_correct_overlaps(elements)
        result = _summarize_canvas_elements(corrected)
        assert result["overlapping_text_pairs"] == 0
        # Original top-to-bottom order preserved
        ys = [el["y"] for el in corrected]
        assert ys == sorted(ys)

    def test_element_that_already_fits_is_not_moved(self):
        elements = [
            {"type": "text", "x": 0, "y": 0, "w": 90, "h": 8, "size": 24, "content": "Short title"},
            {"type": "text", "x": 0, "y": 20, "w": 90, "h": 5, "size": 16, "content": "Body text well below the title, no collision risk here."},
        ]
        corrected = auto_correct_overlaps(elements)
        assert corrected[1]["y"] == 20

    def test_single_text_element_still_gets_height_corrected(self):
        elements = [{"type": "text", "x": 0, "y": 0, "w": 15, "h": 2, "size": 44, "content": "A title long enough to wrap"}]
        corrected = auto_correct_overlaps(elements)
        assert corrected[0]["h"] > 2
