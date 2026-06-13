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
