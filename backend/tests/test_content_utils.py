import pytest
from utils.content_utils import normalize_bullets, normalize_metrics


# ---------------------------------------------------------------------------
# normalize_bullets
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
