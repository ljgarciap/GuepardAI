"""
test_artistic_pdf_legacy_layout.py — Traducción grammar_type -> layout real
del path PDF legacy (Coherencia Artística del Pipeline).

Antes de este fix, render_agent.py pasaba content_json["layout_type"] crudo a
pdf_base.html, que solo reconoce 4 valores explícitos + fallback "split" — 9 de
cada 10 grammar_type colapsaban en silencio. Este test prueba que TODOS los
valores reales que puede emitir el Analyst/Art Director (GRAMMAR_GEOMETRIES +
las 3 extra reconocidas por painter_bridge.GRAMMAR_TO_PAINTER, más cada alias
de SLUG_ALIASES) resuelven a uno de los 5 `layout` que pdf_base.html sabe
renderizar.

Spec: docs/specs/coherencia-artistica-pipeline.md (Acceptance criteria,
"render_agent.py usa GRAMMAR_TO_ARTISTIC_PDF...").
"""
import pytest

from services.ingestion.brand_composition_dna import SLUG_ALIASES
from services.rendering.artistic_pdf_service import (
    GRAMMAR_TO_ARTISTIC_PDF,
    resolve_legacy_pdf_layout,
)

# Los 5 únicos `layout` que pdf_base.html sabe renderizar de forma distinta
# (ver pdf_base.html:118-129) — cualquier otro valor sería un layout fantasma.
KNOWN_LEGACY_LAYOUTS = {"hero", "data_grid", "quote", "pillars", "split"}

# Los 11 grammar_type canónicos que el Analyst (infer_grammar_type) o el Art
# Director LLM pueden asignar a un slide (ver brand_composition_dna.py /
# painter_bridge.GRAMMAR_TO_PAINTER).
CANONICAL_GRAMMAR_TYPES = [
    "strategic_split", "executive_quote", "impact_number", "section_break",
    "case_study", "two_column", "cover_hero", "data_grid_cards",
    "closing_cta", "marketing_hero", "asymmetric_overlay",
]


@pytest.mark.unit
class TestGrammarToArtisticPdfMapping:

    @pytest.mark.parametrize("grammar_type", CANONICAL_GRAMMAR_TYPES)
    def test_every_canonical_grammar_type_resolves_to_a_known_layout(self, grammar_type):
        assert resolve_legacy_pdf_layout(grammar_type) in KNOWN_LEGACY_LAYOUTS

    @pytest.mark.parametrize("alias_slug", list(SLUG_ALIASES.keys()))
    def test_every_slug_alias_resolves_to_a_known_layout(self, alias_slug):
        assert resolve_legacy_pdf_layout(alias_slug) in KNOWN_LEGACY_LAYOUTS

    def test_data_grid_alias_does_not_silently_fall_back_to_split(self):
        # Regresión puntual: "data-grid" (SLUG_ALIASES) resuelve al canónico
        # "data_grid" (sin "_cards") — un valor que no estaba cubierto en la
        # primera versión de GRAMMAR_TO_ARTISTIC_PDF y caía al fallback "split".
        assert resolve_legacy_pdf_layout("data-grid") == "data_grid"
        assert resolve_legacy_pdf_layout("data_grid") == "data_grid"

    def test_unknown_grammar_type_falls_back_to_split(self):
        assert resolve_legacy_pdf_layout("some_future_grammar_type_v99") == "split"

    def test_falsy_input_falls_back_to_split_without_raising(self):
        assert resolve_legacy_pdf_layout(None) == "split"
        assert resolve_legacy_pdf_layout("") == "split"

    def test_list_input_uses_first_element(self):
        # Mismo guard defensivo que get_layout_geometry() en brand_composition_dna.py
        assert resolve_legacy_pdf_layout(["cover_hero"]) == "hero"

    def test_no_mapped_grammar_type_targets_an_unknown_layout(self):
        # Ningún valor de la tabla debe apuntar a un layout que pdf_base.html
        # no reconozca — protege contra un typo silencioso en el mapeo mismo.
        assert set(GRAMMAR_TO_ARTISTIC_PDF.values()) <= KNOWN_LEGACY_LAYOUTS


# El vocabulario real que emite prompt_content_outline_v3 ("Allowed layout_type
# values") — DISTINTO del vocabulario canónico de arriba. render_agent.py nunca
# lee slide.layout_slug en el path PDF legacy, solo content_json["layout_type"],
# así que ESTE es el vocabulario que de verdad llega a resolve_legacy_pdf_layout()
# en producción. Hallazgo (Synthesis Studio v2, docs/specs/synthesis-studio-v2.md,
# Finding 2): antes de este fix, ninguno de estos 4 valores matcheaba una key real
# — solo "data_grid_cards" coincidía por estar en ambos vocabularios — y
# composition_hero/split/pillars/quote colapsaban todos al mismo "split",
# confirmado visualmente (3 slides con layout_type distinto renderizando idénticas).
OUTLINE_LAYOUT_TYPES = [
    "composition_hero", "composition_split", "composition_quote",
    "composition_pillars", "data_grid_cards",
]


@pytest.mark.unit
class TestGrammarToArtisticPdfRecognizesOutlineVocabulary:

    @pytest.mark.parametrize("layout_type", OUTLINE_LAYOUT_TYPES)
    def test_every_outline_layout_type_is_a_real_key_not_the_silent_default(self, layout_type):
        assert layout_type in GRAMMAR_TO_ARTISTIC_PDF, (
            f"'{layout_type}' (vocabulario real de prompt_content_outline_v3) no es "
            f"una key de GRAMMAR_TO_ARTISTIC_PDF — colapsará al fallback 'split' de "
            f"resolve_legacy_pdf_layout(), no a un layout distinto."
        )

    def test_distinct_outline_layout_types_produce_distinct_legacy_layouts(self):
        resolved = {lt: resolve_legacy_pdf_layout(lt) for lt in OUTLINE_LAYOUT_TYPES}
        assert len(set(resolved.values())) == len(OUTLINE_LAYOUT_TYPES), (
            f"Valores del Outline Generator colapsando al mismo layout: {resolved}"
        )
