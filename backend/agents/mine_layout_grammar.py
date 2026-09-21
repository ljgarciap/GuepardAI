"""
mine_layout_grammar.py — MineLayoutGrammarTool (Artistic Generation Engine v2,
Phase 0). docs/specs/artistic-generation-v2.md

Ingestion-side tool: given deterministic geometry clusters (produced by
services/generation/layout_grammar_service.py::cluster_regions()), makes ONE
LLM call to name and classify each cluster into a BrandLayoutGrammar
signature, then persists the result.

Unlike generation-side tools, this does NOT call self.log_decision():
ArtDirectorDecision.job_id is a FK to generation_jobs, which doesn't exist at
ingestion time — the existing ingestion tools (ReadPPTXTool, ExtractPaletteTool
in agents/brand_analyst.py) follow the same precedent and don't call it either.
"""
import json
from typing import Any, List
from pydantic import BaseModel, Field

from agents.base import BaseAgentTool
from database import SessionLocal
import models
# Import del módulo (no del símbolo): el lookup en call-time permite que el
# mock global de conftest sobre providers.llm_provider surta efecto siempre
# (mismo patrón que agents/qa_validator.py).
from providers import llm_provider


class MineLayoutGrammarArgs(BaseModel):
    brand_id: int = Field(..., description="Brand these clusters were mined from")
    source_filename: str = Field(..., description="Source deck/PDF filename")
    clusters: List[dict] = Field(
        ..., description="Deterministic geometry clusters from layout_grammar_service.cluster_regions()"
    )


class MineLayoutGrammarTool(BaseAgentTool):
    name = "mine_layout_grammar"
    description = "Names and classifies deterministic geometry clusters into reusable brand layout signatures."
    args_schema = MineLayoutGrammarArgs

    def run(self, brand_id: int, source_filename: str, clusters: List[dict]) -> dict:
        if not clusters:
            return {"signatures": []}

        raw = llm_provider.generate_json(self._build_prompt(clusters), specialization="general")
        signatures = raw.get("signatures", []) if isinstance(raw, dict) else []

        db = SessionLocal()
        try:
            existing = db.query(models.BrandLayoutGrammar).filter(
                models.BrandLayoutGrammar.brand_id == brand_id,
                models.BrandLayoutGrammar.source_filename == source_filename,
            ).first()
            summary = f"{len(signatures)} signature(s) mined from {len(clusters)} cluster(s)."
            if existing:
                existing.signatures_json = signatures
                existing.raw_extraction = clusters
                existing.mining_summary = summary
            else:
                db.add(models.BrandLayoutGrammar(
                    brand_id=brand_id,
                    source_filename=source_filename,
                    signatures_json=signatures,
                    raw_extraction=clusters,
                    mining_summary=summary,
                ))
            db.commit()
        finally:
            db.close()

        return {"signatures": signatures}

    async def arun(self, **kwargs) -> Any:
        return self.run(**kwargs)

    @staticmethod
    def _build_prompt(clusters: List[dict]) -> str:
        return f"""You are analyzing extracted slide/page geometry from a real brand deck to
identify reusable, named layout signatures for that brand.

Below are geometry clusters — groups of slides/pages that share near-identical
slot positions and repeated decorative shapes:

{json.dumps(clusters, indent=2)}

For EACH cluster, output one named signature. Output ONLY a JSON object:
{{
  "signatures": [
    {{
      "name": "<short kebab-case name specific to what this cluster actually shows>",
      "source_slide_indices": [<from the cluster's page_indices>],
      "content_shape": "<one of: metric_comparison | narrative | quote | cover>",
      "slots": [<copy shared_slots as-is>],
      "motifs": ["<short tag>", ...],
      "confidence": <0.0-1.0, lower if page_indices count is small>
    }}
  ]
}}
"""
