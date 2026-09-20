"""
test_painter_bridge_grammar_mapping.py — GRAMMAR_TO_PAINTER must recognize the
real vocabulary prompt_analyst_v3 instructs the LLM to emit.

Hallazgo (Synthesis Studio v2, sesión de elicitación 2026-09-20): prompt_analyst_v3
("GRAMMAR TYPE RULES: use EXACTLY these values") le pide al LLM elegir entre
hero/split/data_grid/pillars/custom_canvas — pero antes de este fix, GRAMMAR_TO_PAINTER
solo tenía una entrada real para "data_grid"; los otros 4 no matcheaban ninguna key
y GRAMMAR_TO_PAINTER.get(layout_type, "composition_split") colapsaba todo a
"composition_split" en silencio. Confirmado con datos reales: ~70% de las slides de
un deck PPTX real terminaron con el mismo layout pese a que el Analyst había elegido
valores distintos.
"""
import pytest

from services.rendering.painter_bridge import GRAMMAR_TO_PAINTER

# Los valores exactos que dispatcha GammaPainter.render_slides() (painter.py) —
# cualquier otro string cae a paint_split por default ahí también, así que el
# valor traducido DEBE ser uno de estos.
PAINTER_DISPATCH_VALUES = {
    "composition_hero", "composition_split", "big_metric", "composition_quote",
    "composition_pillars", "data_grid_cards", "paint_data_grid_cards", "custom_canvas",
}

# El vocabulario real y completo de prompt_analyst_v3 (utils/seed.py).
ANALYST_VOCABULARY = ["hero", "split", "data_grid", "pillars", "custom_canvas"]


@pytest.mark.unit
class TestGrammarToPainterRecognizesAnalystVocabulary:

    @pytest.mark.parametrize("analyst_value", ANALYST_VOCABULARY)
    def test_every_analyst_value_is_a_real_key_not_the_silent_default(self, analyst_value):
        # Antes del fix esto fallaba para hero/split/pillars/custom_canvas —
        # estaban ausentes de GRAMMAR_TO_PAINTER y devolvían el default del
        # .get() en el call site, nunca un valor explícito de esta tabla.
        assert analyst_value in GRAMMAR_TO_PAINTER, (
            f"'{analyst_value}' (vocabulario real de prompt_analyst_v3) no es una key "
            f"de GRAMMAR_TO_PAINTER — colapsará al default silencioso del .get() en "
            f"render_agent.py, no a un layout distinto."
        )

    @pytest.mark.parametrize("analyst_value", ANALYST_VOCABULARY)
    def test_every_analyst_value_resolves_to_something_the_painter_dispatches(self, analyst_value):
        painted_as = GRAMMAR_TO_PAINTER.get(analyst_value, "composition_split")
        assert painted_as in PAINTER_DISPATCH_VALUES

    def test_distinct_analyst_values_produce_distinct_painted_layouts(self):
        # La razón de ser del fix: hero/split/pillars/data_grid ya NO deben
        # colapsar todos al mismo "composition_split". "custom_canvas" es la
        # única excepción deliberada: paint_custom_canvas() pinta desde
        # slide_data["elements"], que el path PPTX nunca puebla, así que se
        # mapea a composition_split (contenido real) en vez de a un layout
        # vacío — ver el comentario en GRAMMAR_TO_PAINTER.
        values_with_real_content = [v for v in ANALYST_VOCABULARY if v != "custom_canvas"]
        painted = {v: GRAMMAR_TO_PAINTER.get(v, "composition_split") for v in values_with_real_content}
        assert len(set(painted.values())) == len(values_with_real_content), (
            f"Valores del Analyst colapsando al mismo layout pintado: {painted}"
        )

    def test_custom_canvas_intentionally_falls_back_to_split_not_a_blank_layout(self):
        # paint_custom_canvas() requiere slide_data["elements"], que ningún
        # builder llena para el path PPTX (solo PremiumVisualAgent lo hace, y
        # es exclusivo del PDF premium) — dispatch directo produce una slide
        # en blanco. Confirmado con una corrida de producción real
        # (Synthesis Studio v2, 2026-09-20).
        assert GRAMMAR_TO_PAINTER["custom_canvas"] == "composition_split"
