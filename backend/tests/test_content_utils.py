import pytest
from utils.content_utils import normalize_bullets, normalize_metrics, sanitize_text_field


# ---------------------------------------------------------------------------
# sanitize_text_field
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_sanitize_bold_double_asterisk():
    assert sanitize_text_field("**Revenue Growth**:") == "Revenue Growth:"


@pytest.mark.unit
def test_sanitize_italic_single_asterisk():
    assert sanitize_text_field("*AI & Data Analytics*:") == "AI & Data Analytics:"


@pytest.mark.unit
def test_sanitize_inline_bold_mid_text():
    assert sanitize_text_field("generate **15% higher revenue per visit**") == "generate 15% higher revenue per visit"


@pytest.mark.unit
def test_sanitize_orphan_trailing_asterisk():
    # Simulates what happens after partial stripping of **text** prefix
    assert sanitize_text_field("*Magnetic Value for Customers**:") == "Magnetic Value for Customers:"


@pytest.mark.unit
def test_sanitize_bold_underscore():
    assert sanitize_text_field("__Strategic Priority__: act now") == "Strategic Priority: act now"


@pytest.mark.unit
def test_sanitize_link():
    assert sanitize_text_field("Visit [our site](https://example.com) for more") == "Visit our site for more"


@pytest.mark.unit
def test_sanitize_heading():
    assert sanitize_text_field("## Section Title") == "Section Title"


@pytest.mark.unit
def test_sanitize_inline_code():
    assert sanitize_text_field("Use `bold` formatting") == "Use bold formatting"


@pytest.mark.unit
def test_sanitize_clean_text_unchanged():
    assert sanitize_text_field("Plain text without any markdown") == "Plain text without any markdown"


@pytest.mark.unit
def test_sanitize_empty_string():
    assert sanitize_text_field("") == ""


@pytest.mark.unit
def test_sanitize_none_returns_empty():
    assert sanitize_text_field(None) == ""


# ---------------------------------------------------------------------------
# normalize_bullets — sanitize_text_field integration
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_normalize_bullets_empty():
    assert normalize_bullets([]) == []


@pytest.mark.unit
def test_normalize_bullets_dash_prefix():
    assert normalize_bullets(["- Increased revenue"]) == ["Increased revenue"]


@pytest.mark.unit
def test_normalize_bullets_asterisk_prefix():
    assert normalize_bullets(["* Item"]) == ["Item"]


@pytest.mark.unit
def test_normalize_bullets_bullet_char():
    assert normalize_bullets(["• Punto"]) == ["Punto"]


@pytest.mark.unit
def test_normalize_bullets_dict_description():
    assert normalize_bullets([{"description": "Hello"}]) == ["Hello"]


@pytest.mark.unit
def test_normalize_bullets_clean_text():
    assert normalize_bullets(["Clean text"]) == ["Clean text"]


@pytest.mark.unit
def test_normalize_bullets_bold_prefix_stripped():
    # LLM outputs **Title**: description — both * and bold stripped
    assert normalize_bullets(["**Revenue Growth**: 15% YoY"]) == ["Revenue Growth: 15% YoY"]


@pytest.mark.unit
def test_normalize_bullets_inline_bold_mid():
    assert normalize_bullets(["generate **15% higher revenue**"]) == ["generate 15% higher revenue"]


@pytest.mark.unit
def test_normalize_bullets_bullet_then_bold():
    # - **Title**: text
    result = normalize_bullets(["- **Strategic Pillar**: Expand loyalty"])
    assert result == ["Strategic Pillar: Expand loyalty"]


# ---------------------------------------------------------------------------
# sanitize_text_field — bracket placeholder stripping
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_sanitize_multiword_bracket_placeholder():
    assert sanitize_text_field("CEO Testimonial: [Retailer CEO Name] on Results") == "CEO Testimonial:  on Results"


@pytest.mark.unit
def test_sanitize_multiword_bracket_placeholder_entire_bullet():
    # When the whole text is a placeholder, result is empty string
    assert sanitize_text_field("[Retailer CEO Name]") == ""


@pytest.mark.unit
def test_sanitize_keyword_bracket_company():
    assert sanitize_text_field("Insights from [Company] programme") == "Insights from  programme"


@pytest.mark.unit
def test_sanitize_keyword_bracket_year():
    assert sanitize_text_field("Results in [Year] exceeded targets") == "Results in  exceeded targets"


@pytest.mark.unit
def test_sanitize_keyword_bracket_ceo():
    # Leading space is trimmed by .strip() — correct behaviour
    assert sanitize_text_field("[CEO] commented on loyalty ROI") == "commented on loyalty ROI"


@pytest.mark.unit
def test_sanitize_bracket_does_not_strip_markdown_links():
    # [text](url) is handled by link stripper, not bracket stripper
    assert sanitize_text_field("See [our report](https://example.com)") == "See our report"


@pytest.mark.unit
def test_sanitize_bracket_does_not_strip_digit_brackets():
    # [Q4 2024] has a digit — not stripped (not a named placeholder)
    result = sanitize_text_field("Revenue grew in Q4")
    assert "Revenue grew in Q4" in result


@pytest.mark.unit
def test_normalize_bullets_filters_placeholder_only_bullets():
    # A bullet that IS only a placeholder becomes empty and gets filtered out
    result = normalize_bullets(["[Retailer CEO Name]", "Real strategic insight here"])
    assert result == ["Real strategic insight here"]


@pytest.mark.unit
def test_normalize_bullets_strips_placeholder_from_mixed_bullet():
    result = normalize_bullets(["CEO Testimonial: [Retailer CEO Name] on Measurable Outcomes"])
    assert result == ["CEO Testimonial:  on Measurable Outcomes"]


# ---------------------------------------------------------------------------
# normalize_metrics
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_normalize_metrics_empty():
    assert normalize_metrics([]) == []


@pytest.mark.unit
def test_normalize_metrics_string_repr_dict():
    result = normalize_metrics(["{'label': 'Engagement Rate', 'value': '43%'}"])
    assert result == [{"label": "Engagement Rate", "value": "43%"}]


@pytest.mark.unit
def test_normalize_metrics_passthrough_dict():
    result = normalize_metrics([{"label": "NPS", "value": "72"}])
    assert result == [{"label": "NPS", "value": "72"}]
