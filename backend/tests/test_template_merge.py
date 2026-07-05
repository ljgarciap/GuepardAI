"""
test_template_merge.py — Unit tests for the Template Merge Engine.

Covers the pure/mockable logic in services/templates/*: role inference,
char-limit estimation, action classification (analyzer), LLM response
unwrapping and markdown stripping (content), in-place text replacement
preserving run formatting (renderer), and the orchestrator's job lifecycle
and error handling. No DB or real LLM calls — DB and generate_json/search_rag
are mocked so these run without the test container.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.templates.template_config import TemplateMergeConfig
from services.templates import template_analyzer as analyzer_mod
from services.templates import template_content as content_mod
from services.templates import template_merge_orchestrator as orch_mod


def make_config(**overrides) -> TemplateMergeConfig:
    return TemplateMergeConfig(**overrides)


def make_shape(width=0, height=0, top=0, is_placeholder=False, placeholder_type=None):
    shape = SimpleNamespace(width=width, height=height, top=top, is_placeholder=is_placeholder)
    if is_placeholder:
        shape.placeholder_format = SimpleNamespace(type=placeholder_type)
    return shape


# ---------------------------------------------------------------------------
# template_analyzer — _should_include_shape
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_should_include_shape_within_bounds():
    config = make_config()
    shape = make_shape(width=100, height=100)
    assert analyzer_mod._should_include_shape(shape, slide_area_emu=100_000, config=config) is True


@pytest.mark.unit
def test_should_include_shape_rejects_background():
    config = make_config(shape_bg_area_threshold=0.80)
    shape = make_shape(width=1000, height=1000)  # ratio = 1_000_000 / 1_000_000 = 1.0 > 0.80
    assert analyzer_mod._should_include_shape(shape, slide_area_emu=1_000_000, config=config) is False


@pytest.mark.unit
def test_should_include_shape_rejects_decorative_dot():
    config = make_config(shape_min_area_threshold=0.005)
    shape = make_shape(width=10, height=10)  # ratio = 100 / 1_000_000 → tiny
    assert analyzer_mod._should_include_shape(shape, slide_area_emu=1_000_000, config=config) is False


@pytest.mark.unit
def test_should_include_shape_zero_slide_area_defaults_true():
    config = make_config()
    shape = make_shape(width=10, height=10)
    assert analyzer_mod._should_include_shape(shape, slide_area_emu=0, config=config) is True


# ---------------------------------------------------------------------------
# template_analyzer — _infer_role
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_infer_role_placeholder_title():
    from pptx.enum.shapes import PP_PLACEHOLDER
    config = make_config()
    shape = make_shape(is_placeholder=True, placeholder_type=PP_PLACEHOLDER.TITLE)
    assert analyzer_mod._infer_role(shape, slide_height_emu=1000, slide_area_emu=1_000_000, config=config) == "title"


@pytest.mark.unit
def test_infer_role_placeholder_body():
    from pptx.enum.shapes import PP_PLACEHOLDER
    config = make_config()
    shape = make_shape(is_placeholder=True, placeholder_type=PP_PLACEHOLDER.BODY)
    assert analyzer_mod._infer_role(shape, slide_height_emu=1000, slide_area_emu=1_000_000, config=config) == "body"


@pytest.mark.unit
def test_infer_role_non_placeholder_footnote_by_small_area():
    config = make_config(footnote_area_fraction=0.03)
    shape = make_shape(width=10, height=10, top=5000)  # area 100 << 3% of 1_000_000
    assert analyzer_mod._infer_role(shape, slide_height_emu=10000, slide_area_emu=1_000_000, config=config) == "footnote"


@pytest.mark.unit
def test_infer_role_non_placeholder_title_by_top_position():
    config = make_config(footnote_area_fraction=0.001, title_top_fraction=0.20)
    shape = make_shape(width=500, height=500, top=100)  # top(100) < 20% of 10000
    assert analyzer_mod._infer_role(shape, slide_height_emu=10000, slide_area_emu=1_000_000, config=config) == "title"


@pytest.mark.unit
def test_infer_role_non_placeholder_defaults_body():
    config = make_config(footnote_area_fraction=0.001, title_top_fraction=0.05)
    shape = make_shape(width=500, height=500, top=9000)  # not small, not near top
    assert analyzer_mod._infer_role(shape, slide_height_emu=10000, slide_area_emu=1_000_000, config=config) == "body"


# ---------------------------------------------------------------------------
# template_analyzer — _estimate_char_limit
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_estimate_char_limit_title_short_hint_uses_multiplier():
    config = make_config(short_hint_threshold=15, short_hint_title_multiplier=3)
    shape = make_shape()
    assert analyzer_mod._estimate_char_limit(shape, "title", "$45", config) == max(len("$45") * 3, 20)


@pytest.mark.unit
def test_estimate_char_limit_title_long_hint_uses_default():
    config = make_config(title_char_limit=80)
    shape = make_shape()
    hint = "A" * 30  # longer than short_hint_threshold (15)
    assert analyzer_mod._estimate_char_limit(shape, "title", hint, config) == 80


@pytest.mark.unit
def test_estimate_char_limit_footnote_uses_fixed_limit():
    config = make_config(footnote_char_limit=120)
    shape = make_shape()
    assert analyzer_mod._estimate_char_limit(shape, "footnote", "any hint", config) == 120


@pytest.mark.unit
def test_estimate_char_limit_body_short_hint_uses_multiplier():
    config = make_config(short_hint_threshold=15, short_hint_body_multiplier=4)
    shape = make_shape()
    assert analyzer_mod._estimate_char_limit(shape, "body", "23%", config) == max(len("23%") * 4, 30)


@pytest.mark.unit
def test_estimate_char_limit_body_area_based_clamped_to_min():
    config = make_config(body_char_limit_min=80, body_char_limit_max=600, chars_per_sq_inch=30)
    shape = make_shape(width=91440, height=91440)  # 0.1in x 0.1in → tiny estimate, clamps to min
    hint = "A" * 30
    assert analyzer_mod._estimate_char_limit(shape, "body", hint, config) == 80


@pytest.mark.unit
def test_estimate_char_limit_body_area_based_clamped_to_max():
    config = make_config(body_char_limit_min=80, body_char_limit_max=600, chars_per_sq_inch=30)
    shape = make_shape(width=914400 * 20, height=914400 * 20)  # huge box
    hint = "A" * 30
    assert analyzer_mod._estimate_char_limit(shape, "body", hint, config) == 600


# ---------------------------------------------------------------------------
# template_analyzer — _infer_action
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_infer_action_footnote_always_preserved():
    config = make_config()
    assert analyzer_mod._infer_action(is_placeholder=False, role="footnote", hint="anything", config=config) == "preserve"


@pytest.mark.unit
def test_infer_action_preserve_keyword_overrides_length():
    config = make_config(preserve_keywords="confidential,proprietary")
    long_hint = "This document is Confidential " + "x" * 200
    assert analyzer_mod._infer_action(is_placeholder=False, role="body", hint=long_hint, config=config) == "preserve"


@pytest.mark.unit
def test_infer_action_placeholder_always_rewrite():
    config = make_config()
    assert analyzer_mod._infer_action(is_placeholder=True, role="body", hint="", config=config) == "rewrite"


@pytest.mark.unit
def test_infer_action_short_hint_preserved():
    config = make_config(preserve_max_hint_chars=50)
    assert analyzer_mod._infer_action(is_placeholder=False, role="body", hint="Short label", config=config) == "preserve"


@pytest.mark.unit
def test_infer_action_medium_hint_adapt():
    config = make_config(preserve_max_hint_chars=10, adapt_max_hint_chars=150)
    hint = "A" * 100
    assert analyzer_mod._infer_action(is_placeholder=False, role="body", hint=hint, config=config) == "adapt"


@pytest.mark.unit
def test_infer_action_long_hint_rewrite():
    config = make_config(preserve_max_hint_chars=10, adapt_max_hint_chars=50)
    hint = "A" * 200
    assert analyzer_mod._infer_action(is_placeholder=False, role="body", hint=hint, config=config) == "rewrite"


# ---------------------------------------------------------------------------
# template_content — _unwrap_value
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_unwrap_value_plain_string_passthrough():
    assert content_mod._unwrap_value("Hello world", max_bullet_items=6) == "Hello world"


@pytest.mark.unit
def test_unwrap_value_dict_with_content_key():
    value = {"role": "body", "content": "Actual text"}
    assert content_mod._unwrap_value(value, max_bullet_items=6) == "Actual text"


@pytest.mark.unit
def test_unwrap_value_dict_without_known_key_joins_values():
    value = {"foo": "bar", "baz": "qux"}
    result = content_mod._unwrap_value(value, max_bullet_items=6)
    assert "bar" in result and "qux" in result


@pytest.mark.unit
def test_unwrap_value_list_joins_with_newline_and_caps_items():
    value = ["one", "two", "three", "four"]
    result = content_mod._unwrap_value(value, max_bullet_items=2)
    assert result == "one\ntwo"


@pytest.mark.unit
def test_unwrap_value_string_repr_of_dict_is_parsed():
    value = "{'role': 'body', 'content': 'Parsed text'}"
    assert content_mod._unwrap_value(value, max_bullet_items=6) == "Parsed text"


@pytest.mark.unit
def test_unwrap_value_malformed_string_repr_falls_back_to_text():
    value = "{'content': unterminated"
    result = content_mod._unwrap_value(value, max_bullet_items=6)
    assert result == value


# ---------------------------------------------------------------------------
# template_content / template_renderer — _strip_markdown
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("mod", [content_mod, __import__(
    "services.templates.template_renderer", fromlist=["_strip_markdown"]
)])
def test_strip_markdown_removes_bold_italic_headings_bullets(mod):
    assert mod._strip_markdown("**Bold** and *italic*") == "Bold and italic"
    assert mod._strip_markdown("## Heading") == "Heading"
    assert mod._strip_markdown("- bullet item") == "bullet item"
    assert mod._strip_markdown("`code`") == "code"


@pytest.mark.unit
def test_strip_markdown_empty_string():
    assert content_mod._strip_markdown("") == ""
    assert content_mod._strip_markdown(None) is None


# ---------------------------------------------------------------------------
# template_content — _generate_for_slide (mocked LLM + RAG)
# ---------------------------------------------------------------------------

def make_slot(shape_id=1, role="body", action="rewrite", char_limit=80, hint="hint"):
    return analyzer_mod.TextSlot(
        slide_idx=0, shape_id=shape_id, shape_name=f"shape{shape_id}", role=role,
        char_limit=char_limit, hint=hint, is_placeholder=False, action=action,
    )


def make_profile(slots):
    profile = analyzer_mod.SlideProfile(slide_idx=0, slide_width_emu=1, slide_height_emu=1)
    profile.slots = slots
    return profile


@pytest.mark.unit
def test_generate_for_slide_skips_llm_when_all_preserved():
    config = make_config()
    profile = make_profile([make_slot(action="preserve")])
    with patch("services.templates.template_content.generate_json") as mock_llm:
        result = content_mod._generate_for_slide(
            profile=profile, knowledge_filename="doc.pdf", brand_id=1,
            user_prompt="prompt", slide_num=1, total_slides=1, config=config,
        )
    assert result == {}
    mock_llm.assert_not_called()


@pytest.mark.unit
def test_generate_for_slide_maps_shape_ids_to_llm_content():
    config = make_config()
    slot = make_slot(shape_id=42, char_limit=100)
    profile = make_profile([slot])
    with patch("services.templates.template_content.generate_json", return_value={"42": "Generated text"}), \
         patch("services.templates.template_content.search_rag", return_value=["context chunk"]):
        result = content_mod._generate_for_slide(
            profile=profile, knowledge_filename="doc.pdf", brand_id=1,
            user_prompt="prompt", slide_num=1, total_slides=1, config=config,
        )
    assert result == {42: "Generated text"}


@pytest.mark.unit
def test_generate_for_slide_truncates_over_char_limit():
    config = make_config()
    slot = make_slot(shape_id=1, char_limit=10)
    profile = make_profile([slot])
    long_text = "This is a very long sentence that exceeds the limit"
    with patch("services.templates.template_content.generate_json", return_value={"1": long_text}), \
         patch("services.templates.template_content.search_rag", return_value=[]):
        result = content_mod._generate_for_slide(
            profile=profile, knowledge_filename="doc.pdf", brand_id=1,
            user_prompt="prompt", slide_num=1, total_slides=1, config=config,
        )
    assert len(result[1]) <= 11  # char_limit + ellipsis
    assert result[1].endswith("…")


@pytest.mark.unit
def test_generate_for_slide_rag_failure_still_calls_llm():
    config = make_config()
    slot = make_slot(shape_id=1, char_limit=100)
    profile = make_profile([slot])
    with patch("services.templates.template_content.generate_json", return_value={"1": "ok"}) as mock_llm, \
         patch("services.templates.template_content.search_rag", side_effect=RuntimeError("rag down")):
        result = content_mod._generate_for_slide(
            profile=profile, knowledge_filename="doc.pdf", brand_id=1,
            user_prompt="prompt", slide_num=1, total_slides=1, config=config,
        )
    mock_llm.assert_called_once()
    assert result == {1: "ok"}


@pytest.mark.unit
def test_generate_slide_contents_empty_slots_slide_skips_llm():
    config = make_config()
    empty_profile = make_profile([])
    with patch("services.templates.template_content.generate_json") as mock_llm:
        results = content_mod.generate_slide_contents(
            profiles=[empty_profile], knowledge_filename="doc.pdf", brand_id=1,
            user_prompt="prompt", config=config,
        )
    assert results == [{}]
    mock_llm.assert_not_called()


@pytest.mark.unit
def test_generate_slide_contents_per_slide_error_yields_empty_strings():
    config = make_config()
    slot = make_slot(shape_id=7)
    profile = make_profile([slot])
    with patch("services.templates.template_content._generate_for_slide", side_effect=RuntimeError("boom")):
        results = content_mod.generate_slide_contents(
            profiles=[profile], knowledge_filename="doc.pdf", brand_id=1,
            user_prompt="prompt", config=config,
        )
    assert results == [{7: ""}]


# ---------------------------------------------------------------------------
# template_renderer — _replace_text_frame / _capture_base_rpr (real python-pptx objects)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_replace_text_frame_preserves_formatting_and_sets_text():
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from services.templates.template_renderer import _replace_text_frame

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
    tf = box.text_frame
    run = tf.paragraphs[0].add_run()
    run.text = "Original"
    run.font.bold = True
    run.font.size = Pt(24)

    _replace_text_frame(tf, "Replaced text")

    assert tf.paragraphs[0].runs[0].text == "Replaced text"
    assert tf.paragraphs[0].runs[0].font.bold is True
    assert tf.paragraphs[0].runs[0].font.size == Pt(24)


@pytest.mark.unit
def test_replace_text_frame_multiline_creates_soft_breaks():
    from pptx import Presentation
    from pptx.util import Inches
    from services.templates.template_renderer import _replace_text_frame

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(2))
    tf = box.text_frame
    tf.paragraphs[0].add_run().text = "Original"

    _replace_text_frame(tf, "Line one\nLine two")

    full_text = tf.paragraphs[0].text
    assert "Line one" in full_text and "Line two" in full_text


@pytest.mark.unit
def test_inject_slide_content_skips_shapes_not_in_map_and_empty_replacement():
    from pptx import Presentation
    from pptx.util import Inches
    from services.templates.template_renderer import _inject_slide_content

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box1 = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
    box1.text_frame.paragraphs[0].add_run().text = "Keep me (not in map)"
    box2 = slide.shapes.add_textbox(Inches(1), Inches(3), Inches(3), Inches(1))
    box2.text_frame.paragraphs[0].add_run().text = "Original 2"

    content_map = {box2.shape_id: ""}  # empty replacement → keep original
    _inject_slide_content(slide, content_map, slide_idx=0)

    assert box1.text_frame.text == "Keep me (not in map)"
    assert box2.text_frame.text == "Original 2"


# ---------------------------------------------------------------------------
# template_merge_orchestrator — run_template_merge (fully mocked DB + pipeline steps)
# ---------------------------------------------------------------------------

def make_mock_job():
    return SimpleNamespace(
        id=1, brand_id=1, template_asset_id=10, knowledge_filename="doc.pdf",
        prompt="Make it good", status="pending", current_step=None, progress=0,
        output_path=None, error_detail=None, display_name=None, updated_at=None,
    )


@pytest.mark.unit
def test_run_template_merge_happy_path_sets_completed():
    job = make_mock_job()
    template_asset = SimpleNamespace(local_path="templates/deck.pptx")

    mock_db = MagicMock()
    mock_db.query.return_value.get.side_effect = lambda id_: (
        job if id_ == job.id else template_asset
    )

    with patch.object(orch_mod, "SessionLocal", return_value=mock_db), \
         patch.object(orch_mod, "resolve_storage", return_value="/tmp/deck.pptx"), \
         patch("os.path.isfile", return_value=True), \
         patch.object(orch_mod, "analyze_template", return_value=["profile1"]), \
         patch.object(orch_mod, "generate_slide_contents", return_value=[{1: "text"}]), \
         patch.object(orch_mod, "render_merged_pptx", return_value="/tmp/out.pptx"), \
         patch.object(orch_mod, "job_dir", return_value="/tmp/jobs/tm_1"), \
         patch.object(orch_mod, "to_relative", return_value="jobs/tm_1/deck_merged.pptx"):
        orch_mod.run_template_merge(job_id=1)

    assert job.status == "completed"
    assert job.progress == 100
    assert job.output_path == "jobs/tm_1/deck_merged.pptx"


@pytest.mark.unit
def test_run_template_merge_missing_job_logs_and_returns():
    mock_db = MagicMock()
    mock_db.query.return_value.get.return_value = None

    with patch.object(orch_mod, "SessionLocal", return_value=mock_db):
        orch_mod.run_template_merge(job_id=999)  # must not raise

    mock_db.close.assert_called_once()


@pytest.mark.unit
def test_run_template_merge_missing_template_asset_marks_error():
    job = make_mock_job()

    mock_db = MagicMock()
    mock_db.query.return_value.get.side_effect = lambda id_: (
        job if id_ == job.id else None
    )
    mock_db2 = MagicMock()
    mock_db2.query.return_value.get.return_value = job

    with patch.object(orch_mod, "SessionLocal", side_effect=[mock_db, mock_db2]):
        orch_mod.run_template_merge(job_id=1)

    assert job.status == "error"
    assert "not found" in job.error_detail


@pytest.mark.unit
def test_run_template_merge_missing_file_on_disk_marks_error():
    job = make_mock_job()
    template_asset = SimpleNamespace(local_path="templates/deck.pptx")

    mock_db = MagicMock()
    mock_db.query.return_value.get.side_effect = lambda id_: (
        job if id_ == job.id else template_asset
    )
    mock_db2 = MagicMock()
    mock_db2.query.return_value.get.return_value = job

    with patch.object(orch_mod, "SessionLocal", side_effect=[mock_db, mock_db2]), \
         patch.object(orch_mod, "resolve_storage", return_value=None):
        orch_mod.run_template_merge(job_id=1)

    assert job.status == "error"
    assert "not found on disk" in job.error_detail


@pytest.mark.unit
def test_run_template_merge_render_failure_marks_error_not_completed():
    job = make_mock_job()
    template_asset = SimpleNamespace(local_path="templates/deck.pptx")

    mock_db = MagicMock()
    mock_db.query.return_value.get.side_effect = lambda id_: (
        job if id_ == job.id else template_asset
    )
    mock_db2 = MagicMock()
    mock_db2.query.return_value.get.return_value = job

    with patch.object(orch_mod, "SessionLocal", side_effect=[mock_db, mock_db2]), \
         patch.object(orch_mod, "resolve_storage", return_value="/tmp/deck.pptx"), \
         patch("os.path.isfile", return_value=True), \
         patch.object(orch_mod, "analyze_template", return_value=["profile1"]), \
         patch.object(orch_mod, "generate_slide_contents", return_value=[{1: "text"}]), \
         patch.object(orch_mod, "render_merged_pptx", side_effect=RuntimeError("render exploded")), \
         patch.object(orch_mod, "job_dir", return_value="/tmp/jobs/tm_1"):
        orch_mod.run_template_merge(job_id=1)

    assert job.status == "error"
    assert "render exploded" in job.error_detail


@pytest.mark.unit
def test_set_status_updates_job_fields_and_commits():
    job = make_mock_job()
    mock_db = MagicMock()

    orch_mod._set_status(mock_db, job, "processing", "Doing work...", 42)

    assert job.status == "processing"
    assert job.current_step == "Doing work..."
    assert job.progress == 42
    mock_db.commit.assert_called_once()
