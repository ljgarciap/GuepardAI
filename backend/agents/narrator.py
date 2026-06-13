import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from agents.base import BaseAgentTool
from database import SessionLocal
from providers.llm_provider import generate_json
import models

_log = logging.getLogger(__name__)

_ALLOWED_FIELDS = {"subtitle", "bullets", "objective"}


class NarratorArgs(BaseModel):
    job_id: int = Field(..., description="ID del GenerationJob")
    slides_data: list = Field(..., description="Lista de dicts de slides post-generación")
    brand_name: str = Field(..., description="Nombre de la marca")
    region: str = Field("Global", description="Idioma/región objetivo")
    strategic_context: str = Field("", description="Framing estratégico global (polished_prompt[:400])")


class NarratorTool(BaseAgentTool):
    name = "narrator"
    description = (
        "Revisa el deck completo post-generación y aplica correcciones quirúrgicas "
        "de cohesión narrativa. Modifica únicamente subtitle, bullets u objective. "
        "Nunca bloquea el pipeline: en caso de fallo devuelve slides_data sin modificar."
    )
    args_schema = NarratorArgs

    def run(
        self,
        job_id: int,
        slides_data: list,
        brand_name: str,
        region: str = "Global",
        strategic_context: str = "",
    ) -> list:
        db = SessionLocal()
        try:
            cfg = (
                db.query(models.SystemConfig)
                .filter(models.SystemConfig.key == "prompt_narrator_v1")
                .first()
            )
            if not cfg:
                _log.warning("[NarratorTool] prompt_narrator_v1 not seeded — skipping cohesion pass")
                return slides_data

            compact_slides = [
                {
                    "idx": i,
                    "title": s.get("title", ""),
                    "subtitle": s.get("subtitle") or "",
                    "bullets": (s.get("bullets") or [])[:3],
                    "layout_type": s.get("layout_type", ""),
                    "section_label": s.get("section_label", ""),
                }
                for i, s in enumerate(slides_data)
            ]

            narrator_prompt = cfg.value.format(
                slides_json=json.dumps(compact_slides, ensure_ascii=False, indent=2),
                brand_name=brand_name,
                target_lang=region,
                strategic_context=str(strategic_context or "")[:400],
                slide_count=len(slides_data),
            )

            try:
                response = generate_json(narrator_prompt, specialization="design")
                if not isinstance(response, dict):
                    response = {}
            except Exception as e:
                _log.warning(f"[NarratorTool] LLM call failed: {e} — returning original slides")
                return slides_data

            corrections = response.get("corrections", [])
            cohesion_score = response.get("cohesion_score", 0)
            gaps_found = response.get("gaps_found", [])

            if not corrections:
                self.log_decision(
                    db=db,
                    job_id=job_id,
                    decision_type="narrator_correction",
                    summary=f"Narrator: no cohesion gaps found (score={cohesion_score})",
                    reasoning=json.dumps({"gaps_found": gaps_found}, ensure_ascii=False),
                    metadata={"cohesion_score": cohesion_score, "corrections_applied": 0, "slide_count": len(slides_data)},
                )
                db.commit()
                return slides_data

            max_corrections = max(1, int(len(slides_data) * 0.4))
            applied = []

            for correction in corrections[:max_corrections]:
                idx = correction.get("slide_index")
                field = correction.get("field")
                new_value = correction.get("new_value")
                reason = correction.get("reason", "")

                if idx is None or field not in _ALLOWED_FIELDS:
                    continue
                if not isinstance(idx, int) or not (0 <= idx < len(slides_data)):
                    continue
                if not new_value:
                    continue

                slides_data[idx][field] = new_value
                applied.append({"idx": idx, "field": field, "reason": reason})

            self.log_decision(
                db=db,
                job_id=job_id,
                decision_type="narrator_correction",
                summary=(
                    f"Narrator applied {len(applied)} correction(s) to {len(slides_data)} slides "
                    f"(cohesion_score={cohesion_score})"
                ),
                reasoning=json.dumps(
                    {"gaps_found": gaps_found, "corrections": applied},
                    ensure_ascii=False,
                ),
                prompt_used=narrator_prompt[:800],
                response_raw=response,
                metadata={
                    "cohesion_score": cohesion_score,
                    "corrections_applied": len(applied),
                    "slide_count": len(slides_data),
                },
            )
            db.commit()
            return slides_data

        except Exception as e:
            _log.warning(f"[NarratorTool] Unexpected error (non-blocking): {e}")
            return slides_data
        finally:
            db.close()

    async def arun(self, **kwargs) -> Any:
        return self.run(**kwargs)
