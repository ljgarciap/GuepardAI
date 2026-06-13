"""
Tests para NarratorTool — agente de cohesión narrativa post-generación.

Todos son @pytest.mark.unit: mockean agents.narrator.SessionLocal y
agents.narrator.generate_json — no requieren BD de test.
"""
import pytest
from unittest.mock import MagicMock, patch
from agents.narrator import NarratorTool


MINIMAL_PROMPT = (
    "Analyze deck for {brand_name} in {target_lang}. "
    "Slides: {slides_json}. Context: {strategic_context}. Count: {slide_count}"
)

SAMPLE_SLIDES = [
    {"title": "Why Partner with Us", "subtitle": None, "bullets": [], "layout_type": "full_bleed_hero", "section_label": "PARTNERSHIP", "objective": ""},
    {"title": "Our Reach", "subtitle": "We are everywhere", "bullets": ["23M households"], "layout_type": "editorial_split", "section_label": "PARTNERSHIP", "objective": ""},
    {"title": "Proven ROI", "subtitle": None, "bullets": ["15% uplift"], "layout_type": "data_cards_brand_grid", "section_label": "RESULTS", "objective": ""},
]


def _make_mock_db(prompt_value=MINIMAL_PROMPT):
    mock_cfg = MagicMock()
    mock_cfg.value = prompt_value
    mock_cfg.key = "prompt_narrator_v1"
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_cfg
    return mock_db


def _call_tool(mock_db, mock_llm_response, slides=None):
    """Patches narrator-local references and calls NarratorTool via __call__."""
    if slides is None:
        slides = [s.copy() for s in SAMPLE_SLIDES]

    with patch("agents.narrator.SessionLocal", return_value=mock_db), \
         patch("agents.narrator.generate_json", return_value=mock_llm_response):
        tool = NarratorTool()
        return tool(
            job_id=1,
            slides_data=slides,
            brand_name="TestBrand",
            region="UK",
            strategic_context="Global loyalty strategy",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Core behaviour
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_narrator_no_corrections_returns_slides_unchanged(mock_llm_calls):
    mock_db = _make_mock_db()
    response = {"corrections": [], "cohesion_score": 0.95, "gaps_found": []}
    result = _call_tool(mock_db, response)
    assert len(result) == len(SAMPLE_SLIDES)
    assert result[0]["subtitle"] is None


@pytest.mark.unit
def test_narrator_applies_subtitle_correction(mock_llm_calls):
    mock_db = _make_mock_db()
    response = {
        "corrections": [
            {"slide_index": 0, "field": "subtitle", "new_value": "Four reasons loyalty drives ROI", "reason": "Section opener lacks preview"}
        ],
        "cohesion_score": 0.6,
        "gaps_found": ["slide 0 opener has no subtitle"],
    }
    result = _call_tool(mock_db, response)
    assert result[0]["subtitle"] == "Four reasons loyalty drives ROI"
    assert result[1]["subtitle"] == "We are everywhere"  # untouched


@pytest.mark.unit
def test_narrator_applies_bullets_correction(mock_llm_calls):
    mock_db = _make_mock_db()
    new_bullets = ["23M Clubcard households", "Market leader in UK loyalty", "Data from 30+ years"]
    response = {
        "corrections": [
            {"slide_index": 1, "field": "bullets", "new_value": new_bullets, "reason": "Bullets don't echo section opener promise"}
        ],
        "cohesion_score": 0.7,
        "gaps_found": ["slide 1 disconnect"],
    }
    result = _call_tool(mock_db, response)
    assert result[1]["bullets"] == new_bullets


@pytest.mark.unit
def test_narrator_applies_objective_correction(mock_llm_calls):
    mock_db = _make_mock_db()
    response = {
        "corrections": [
            {"slide_index": 2, "field": "objective", "new_value": "Demonstrate measurable partner ROI", "reason": "Objective was empty"}
        ],
        "cohesion_score": 0.75,
        "gaps_found": [],
    }
    result = _call_tool(mock_db, response)
    assert result[2]["objective"] == "Demonstrate measurable partner ROI"


# ─────────────────────────────────────────────────────────────────────────────
# Guard rails
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_narrator_disallowed_field_title_is_skipped(mock_llm_calls):
    mock_db = _make_mock_db()
    response = {
        "corrections": [
            {"slide_index": 0, "field": "title", "new_value": "Injected title", "reason": "test"}
        ],
        "cohesion_score": 0.5,
        "gaps_found": [],
    }
    result = _call_tool(mock_db, response)
    assert result[0]["title"] == "Why Partner with Us"


@pytest.mark.unit
def test_narrator_out_of_range_index_is_skipped(mock_llm_calls):
    mock_db = _make_mock_db()
    response = {
        "corrections": [
            {"slide_index": 99, "field": "subtitle", "new_value": "Phantom slide", "reason": "test"}
        ],
        "cohesion_score": 0.5,
        "gaps_found": [],
    }
    result = _call_tool(mock_db, response)
    assert len(result) == len(SAMPLE_SLIDES)


@pytest.mark.unit
def test_narrator_empty_new_value_is_skipped(mock_llm_calls):
    mock_db = _make_mock_db()
    response = {
        "corrections": [
            {"slide_index": 0, "field": "subtitle", "new_value": "", "reason": "empty"}
        ],
        "cohesion_score": 0.6,
        "gaps_found": [],
    }
    result = _call_tool(mock_db, response)
    assert result[0]["subtitle"] is None


@pytest.mark.unit
def test_narrator_respects_40pct_correction_limit(mock_llm_calls):
    # 5 slides → max 2 corrections (max(1, int(5 * 0.4)) = 2)
    slides = [
        {"title": f"Slide {i}", "subtitle": None, "bullets": [], "layout_type": "editorial_split", "section_label": "S", "objective": ""}
        for i in range(5)
    ]
    mock_db = _make_mock_db()
    response = {
        "corrections": [
            {"slide_index": i, "field": "subtitle", "new_value": f"Fixed {i}", "reason": "test"}
            for i in range(5)
        ],
        "cohesion_score": 0.3,
        "gaps_found": ["all slides disconnected"],
    }
    result = _call_tool(mock_db, response, slides=slides)
    fixed = [s for s in result if s.get("subtitle") and str(s["subtitle"]).startswith("Fixed")]
    assert len(fixed) <= 2


# ─────────────────────────────────────────────────────────────────────────────
# Resilience
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_narrator_llm_failure_returns_original_slides(mock_llm_calls):
    mock_db = _make_mock_db()
    slides = [s.copy() for s in SAMPLE_SLIDES]

    with patch("agents.narrator.SessionLocal", return_value=mock_db), \
         patch("agents.narrator.generate_json", side_effect=Exception("LLM timeout")):
        tool = NarratorTool()
        result = tool(
            job_id=1,
            slides_data=slides,
            brand_name="TestBrand",
            region="UK",
            strategic_context="",
        )

    # Pydantic creates a new list in .dict(), so compare by value not identity
    assert result == slides


@pytest.mark.unit
def test_narrator_no_prompt_seeded_returns_slides_unchanged(mock_llm_calls):
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    slides = [s.copy() for s in SAMPLE_SLIDES]
    with patch("agents.narrator.SessionLocal", return_value=mock_db):
        tool = NarratorTool()
        result = tool(
            job_id=1,
            slides_data=slides,
            brand_name="TestBrand",
            region="UK",
            strategic_context="",
        )

    assert result == slides


@pytest.mark.unit
def test_narrator_llm_returns_non_dict_is_handled(mock_llm_calls):
    mock_db = _make_mock_db()
    slides = [s.copy() for s in SAMPLE_SLIDES]

    with patch("agents.narrator.SessionLocal", return_value=mock_db), \
         patch("agents.narrator.generate_json", return_value=["unexpected", "list"]):
        tool = NarratorTool()
        result = tool(
            job_id=1,
            slides_data=slides,
            brand_name="TestBrand",
            region="UK",
            strategic_context="",
        )

    assert len(result) == len(SAMPLE_SLIDES)
