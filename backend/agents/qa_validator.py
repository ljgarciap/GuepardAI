import json
from typing import Any, Dict, List
from pydantic import BaseModel, Field
from agents.base import BaseAgentTool

from database import SessionLocal
import models
from providers.llm_provider import generate_json

class ValidateBrandArgs(BaseModel):
    job_id: int = Field(..., description="ID del trabajo a validar")

class ValidateBrandTool(BaseAgentTool):
    name = "validate_brand"
    description = "Validador determinista: revisa que no se rompan reglas fundamentales físicas (ej: usar un logo como fondo de pantalla)."
    args_schema = ValidateBrandArgs

    def run(self, job_id: int) -> Dict[str, Any]:
        db = SessionLocal()
        violations = []
        try:
            slides = db.query(models.PresentationSlide).filter(
                models.PresentationSlide.job_id == job_id,
                models.PresentationSlide.status == "planned"
            ).all()

            for slide in slides:
                # Regla Determinista 1: Logos como fondos de alta resolución
                layout = slide.layout_slug or ""
                requires_hi_res = layout in ["cover_hero", "full_brand_overlay", "big_image", "full_bleed"] or "split" in layout
                
                # Check assigned image
                img_val = slide.assigned_image
                if img_val:
                    # En la BD el assigned_image suele guardar el basename o el ID
                    # Intentamos inferir la categoría si es posible
                    asset_rec = None
                    if str(img_val).isdigit():
                        asset_rec = db.query(models.BrandAsset).get(int(img_val))
                    else:
                        asset_rec = db.query(models.BrandAsset).filter(
                            models.BrandAsset.local_path.contains(str(img_val))
                        ).first()

                    if asset_rec and requires_hi_res and asset_rec.category in ["logos", "icons"]:
                        violations.append({
                            "slide_number": slide.slide_number,
                            "rule": "HI_RES_BACKGROUND_VIOLATION",
                            "message": f"El slide usa un {asset_rec.category} como imagen principal en un layout que exige foto de alta resolución ({layout})."
                        })

                # Puedes agregar más reglas deterministas aquí
                # Ejemplo: Slide text demasiado largo para un impact_number, etc.

            result_status = "passed" if not violations else "failed"

            # GAP 1: Trazar decisión determinística en ArtDirectorDecision
            self.log_decision(
                db=db,
                job_id=job_id,
                decision_type="brand_violation",
                summary=f"Deterministic QA: {result_status.upper()} — {len(violations)} violation(s) found.",
                reasoning="",
                metadata={"violations": violations, "total_slides_checked": len(slides)},
            )
            db.commit()

            return {"status": result_status, "violations": violations}
        finally:
            db.close()

    async def arun(self, **kwargs) -> Any:
        return self.run(**kwargs)


class ScoreFidelityArgs(BaseModel):
    job_id: int = Field(..., description="ID del trabajo a evaluar")
    threshold: float = Field(0.8, description="Umbral mínimo para considerar el pase exitoso")

class ScoreFidelityTool(BaseAgentTool):
    name = "score_fidelity"
    description = "Validador Híbrido (LLM): actúa como juez evaluando la coherencia semántica del diseño seleccionado frente a la identidad de marca."
    args_schema = ScoreFidelityArgs

    def run(self, job_id: int, threshold: float = 0.8) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            job = db.query(models.GenerationJob).get(job_id)
            if not job:
                return {"error": "Job not found"}

            slides = db.query(models.PresentationSlide).filter(
                models.PresentationSlide.job_id == job_id,
                models.PresentationSlide.status == "planned"
            ).all()

            dna = db.query(models.BrandVisualDna).filter(models.BrandVisualDna.brand_id == job.brand_id).first()
            essence = db.query(models.BrandArtisticEssence).filter(models.BrandArtisticEssence.brand_id == job.brand_id).first()

            if not slides or not dna:
                return {"score": 1.0, "needs_rework": False, "reasoning": "Missing data for QA, auto-passing."}

            # Preparamos contexto para el LLM Juez
            brand_context = {
                "primary_color": dna.primary_color,
                "strategy": essence.art_direction_note if essence else "Corporate standard"
            }

            slides_context = []
            for s in slides:
                slides_context.append({
                    "number": s.slide_number,
                    "title": s.title,
                    "layout_selected": s.layout_slug,
                    "planning_reasoning": s.planning_json.get("art_director", {}).get("reasoning", "") if s.planning_json else ""
                })

            prompt = f"""
            You are a strict QA Brand Validator.
            Evaluate the following presentation design plan against the brand strategy.
            
            BRAND STRATEGY:
            {json.dumps(brand_context)}
            
            SLIDES PLANNED:
            {json.dumps(slides_context)}
            
            Determine if the selected layouts and reasoning match the brand's tone.
            Output JSON:
            {{
                "score": 0.0 to 1.0,
                "needs_rework": true/false,
                "reasoning": "Explanation"
            }}
            """

            result = generate_json(prompt, specialization="general")
            score = float(result.get("score", 1.0))
            needs_rework = bool(result.get("needs_rework", score < threshold))
            reasoning = result.get("reasoning", "")

            if needs_rework:
                job.status = "qa_failed"
                job.current_step = "QA Validator rejected the layout plan. Needs rework."
            else:
                job.status = "qa_passed"
                job.current_step = "QA Validator approved the layout plan."

            # GAP 1: Trazar veredicto del LLM Juez en ArtDirectorDecision
            self.log_decision(
                db=db,
                job_id=job_id,
                decision_type="qa_score",
                summary=f"LLM QA Judge: score={score:.2f}, needs_rework={needs_rework}",
                reasoning=reasoning,
                prompt_used=prompt,
                response_raw=result,
                metadata={"score": score, "threshold": threshold, "needs_rework": needs_rework},
            )
            db.commit()

            return {
                "score": score,
                "needs_rework": needs_rework,
                "reasoning": reasoning
            }
        finally:
            db.close()

    async def arun(self, **kwargs) -> Any:
        return self.run(**kwargs)
