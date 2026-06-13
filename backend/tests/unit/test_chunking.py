import pytest
from services.ingestion.ingest_knowledge import chunk_text_paragraphs, extract_slides_from_pptx
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# chunk_text_paragraphs
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_single_paragraph_returns_one_chunk():
    text = "This is a paragraph with enough content to qualify."
    result = chunk_text_paragraphs(text, max_chars=500)
    assert len(result) == 1
    assert result[0] == text


@pytest.mark.unit
def test_two_short_paragraphs_merged_into_one_chunk():
    text = "First paragraph.\n\nSecond paragraph."
    result = chunk_text_paragraphs(text, max_chars=500)
    assert len(result) == 1
    assert "First paragraph." in result[0]
    assert "Second paragraph." in result[0]


@pytest.mark.unit
def test_long_paragraphs_split_into_multiple_chunks():
    para = "A" * 600
    text = f"{para}\n\n{para}"
    result = chunk_text_paragraphs(text, max_chars=700)
    assert len(result) >= 2


@pytest.mark.unit
def test_overlap_carries_tail_of_previous_chunk():
    para1 = "First paragraph with enough content. " * 20  # ~720 chars
    para2 = "Second paragraph with independent content. " * 5
    text = f"{para1}\n\n{para2}"
    result = chunk_text_paragraphs(text, max_chars=800, overlap=100)
    # The second chunk should contain overlap from the first
    assert len(result) >= 2
    # Tail of para1 should appear in the second chunk (overlap)
    combined = " ".join(result)
    assert "First paragraph" in combined


@pytest.mark.unit
def test_skips_blank_paragraphs():
    text = "Real content.\n\n   \n\nMore content."
    result = chunk_text_paragraphs(text, max_chars=500)
    for chunk in result:
        assert chunk.strip() != ""


@pytest.mark.unit
def test_empty_text_returns_empty_list():
    assert chunk_text_paragraphs("") == []


@pytest.mark.unit
def test_whitespace_only_text_returns_empty_list():
    assert chunk_text_paragraphs("   \n\n   \n\n   ") == []


@pytest.mark.unit
def test_paragraph_shorter_than_min_length_excluded():
    text = "Hi\n\nThis is a proper paragraph with real content."
    result = chunk_text_paragraphs(text, max_chars=500)
    # "Hi" alone is 2 chars, below the 5-char minimum
    assert len(result) == 1
    assert "proper paragraph" in result[0]


# ---------------------------------------------------------------------------
# extract_slides_from_pptx — mocked via pptx.Presentation
# ---------------------------------------------------------------------------

def _make_mock_pptx(slides_texts):
    """Build a minimal mock Presentation with slides containing shapes."""
    mock_prs = MagicMock()
    mock_slides = []
    for texts in slides_texts:
        mock_slide = MagicMock()
        shapes = []
        for t in texts:
            shape = MagicMock()
            shape.text = t
            shapes.append(shape)
        mock_slide.shapes = shapes
        mock_slides.append(mock_slide)
    mock_prs.slides = mock_slides
    return mock_prs


@pytest.mark.unit
def test_extract_slides_returns_one_chunk_per_slide():
    with patch("services.ingestion.ingest_knowledge.Presentation") as mock_pptx:
        mock_pptx.return_value = _make_mock_pptx([
            ["Title A", "Bullet 1", "Bullet 2"],
            ["Title B", "Content here"],
        ])
        result = extract_slides_from_pptx("fake.pptx")

    assert len(result) == 2
    assert result[0]["metadata"]["slide_number"] == 1
    assert result[1]["metadata"]["slide_number"] == 2
    assert result[0]["metadata"]["chunk_type"] == "slide"


@pytest.mark.unit
def test_extract_slides_concatenates_shapes_per_slide():
    with patch("services.ingestion.ingest_knowledge.Presentation") as mock_pptx:
        mock_pptx.return_value = _make_mock_pptx([
            ["Revenue Growth", "15% YoY", "Key driver: loyalty programme"],
        ])
        result = extract_slides_from_pptx("fake.pptx")

    assert "Revenue Growth" in result[0]["text"]
    assert "15% YoY" in result[0]["text"]


@pytest.mark.unit
def test_extract_slides_skips_empty_slides():
    with patch("services.ingestion.ingest_knowledge.Presentation") as mock_pptx:
        mock_pptx.return_value = _make_mock_pptx([
            ["Real content here"],
            ["   ", ""],          # empty slide — shapes with only whitespace
            ["Another real slide"],
        ])
        result = extract_slides_from_pptx("fake.pptx")

    assert len(result) == 2
    slide_numbers = [r["metadata"]["slide_number"] for r in result]
    assert 1 in slide_numbers
    assert 3 in slide_numbers
