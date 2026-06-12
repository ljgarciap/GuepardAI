import json
import os
from typing import Any, Dict, List
from pydantic import BaseModel, Field
from agents.base import BaseAgentTool

from database import SessionLocal
import models
# Import del módulo (no del símbolo): el lookup en call-time permite que el
# mock global de conftest sobre providers.llm_provider surta efecto siempre
from providers import llm_provider

def _resolve_assigned_asset(db, img_val):
    """
    Resuelve el BrandAsset detrás de PresentationSlide.assigned_image, que puede
    guardar el ID numérico o el basename del archivo. Compartido por el
    validador determinista y el juez LLM (Calidad Selección v2).
    """
    if not img_val:
        return None
    if str(img_val).isdigit():
        return db.query(models.BrandAsset).get(int(img_val))
    return db.query(models.BrandAsset).filter(
        models.BrandAsset.local_path.contains(str(img_val))
    ).first()


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
                models.PresentationSlide.status == models.PresentationSlideStatus.PLANNED
            ).all()

            # Regla única de hi-res y resolución de dimensiones compartidas con la
            # Fase B del Art Director (Calidad Selección v2)
            from services.generation.art_director_service import _requires_hi_res, _resolve_asset_dims

            # Grupos de duplicados: gemelos visuales comparten perceptual_hash;
            # sin hash (pre-backfill) el grupo cae al ID exacto del asset
            duplicate_groups = {}

            for slide in slides:
                # Regla Determinista 1: Logos como fondos de alta resolución
                layout = slide.layout_slug or ""
                requires_hi_res = layout in ["cover_hero", "full_brand_overlay", "big_image", "full_bleed"] or "split" in layout

                asset_rec = _resolve_assigned_asset(db, slide.assigned_image)
                if asset_rec:
                    if requires_hi_res and asset_rec.category in ["logos", "icons"]:
                        violations.append({
                            "slide_number": slide.slide_number,
                            "rule": "HI_RES_BACKGROUND_VIOLATION",
                            "message": f"El slide usa un {asset_rec.category} como imagen principal en un layout que exige foto de alta resolución ({layout})."
                        })

                    # Regla Determinista 2 (Calidad Selección v2): resolución
                    # insuficiente para el layout FINAL del slide. Sin dimensiones
                    # conocidas el criterio no aplica.
                    min_required = 1200 if _requires_hi_res(layout) else 800
                    width, _ = _resolve_asset_dims(asset_rec)
                    if width and width < min_required:
                        violations.append({
                            "slide_number": slide.slide_number,
                            "rule": "LOW_RESOLUTION_IMAGE",
                            "message": f"El slide usa una imagen de {width}px de ancho en un layout '{layout}' que exige al menos {min_required}px (se verá pixelada)."
                        })

                    # Regla Determinista 3 (Calidad Selección v2): acumular para
                    # detección de imagen duplicada entre slides
                    group_key = asset_rec.perceptual_hash or f"id:{asset_rec.id}"
                    duplicate_groups.setdefault(group_key, []).append(slide.slide_number)

            for group_key, slide_numbers in duplicate_groups.items():
                if len(slide_numbers) > 1:
                    violations.append({
                        "slide_number": slide_numbers[-1],
                        "rule": "DUPLICATE_IMAGE_ACROSS_SLIDES",
                        "all_slide_numbers": slide_numbers,
                        "message": f"La misma imagen (o una variante visual idéntica) está asignada a los slides {sorted(slide_numbers)}. Cada slide debe usar una imagen distinta."
                    })

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
                models.PresentationSlide.status == models.PresentationSlideStatus.PLANNED
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
                ad_plan = s.planning_json.get("art_director", {}) if s.planning_json else {}

                # Calidad Selección v2: el juez ahora VE la imagen asignada
                # (archivo, dimensiones, categoría, descripción, flag degraded)
                image_context = None
                asset_rec = _resolve_assigned_asset(db, s.assigned_image)
                if asset_rec:
                    image_context = {
                        "file": os.path.basename(asset_rec.local_path or ""),
                        "width": asset_rec.width,
                        "height": asset_rec.height,
                        "category": asset_rec.category,
                        "description": (asset_rec.description or "")[:80],
                    }

                slides_context.append({
                    "number": s.slide_number,
                    "title": s.title,
                    "layout_selected": s.layout_slug,
                    "assigned_image": image_context,
                    "degraded_asset_quality": bool(ad_plan.get("degraded")),
                    "planning_reasoning": ad_plan.get("reasoning", "")
                })

            prompt = f"""
            You are a strict QA Brand Validator.
            Evaluate the following presentation design plan against the brand strategy.
            
            BRAND STRATEGY:
            {json.dumps(brand_context)}
            
            SLIDES PLANNED:
            {json.dumps(slides_context)}
            
            Determine if the selected layouts and reasoning match the brand's tone.
            Also weigh the assigned_image of each slide: penalize visually repetitive
            image choices across slides and slides whose degraded_asset_quality is true
            (the image did not meet the quality bar and was admitted as a last resort).
            Output JSON:
            {{
                "score": 0.0 to 1.0,
                "needs_rework": true/false,
                "reasoning": "Explanation"
            }}
            """

            # Threshold de runtime (spec qa-judge-verdict-consistency): el arg
            # del tool solo es fallback si la config no parsea
            try:
                threshold = float(llm_provider.get_system_config("qa_fidelity_threshold", str(threshold)))
            except (TypeError, ValueError):
                pass

            result = llm_provider.generate_json(prompt, specialization="general")

            # El score numérico contra el threshold es la autoridad del veredicto;
            # la flag del LLM es opinión auditada (spec qa-judge-verdict-consistency)
            try:
                score = max(0.0, min(1.0, float(result.get("score"))))
            except (TypeError, ValueError):
                score = None

            llm_flag = result.get("needs_rework")
            if isinstance(llm_flag, str):
                llm_flag = llm_flag.strip().lower() == "true"
            elif llm_flag is not None:
                llm_flag = bool(llm_flag)

            if score is not None:
                needs_rework = score < threshold
            elif llm_flag is not None:
                needs_rework = llm_flag  # fallback 1: sin score parseable, decide la flag
            else:
                needs_rework = False      # fallback 2: fail-open, como el auto-pass por datos ausentes

            llm_flag_overridden = score is not None and llm_flag is not None and llm_flag != needs_rework
            reasoning = result.get("reasoning", "")

            if needs_rework:
                job.status = models.GenerationJobStatus.QA_FAILED
                job.current_step = "QA Validator rejected the layout plan. Needs rework."
            else:
                job.status = models.GenerationJobStatus.QA_PASSED
                job.current_step = "QA Validator approved the layout plan."

            # GAP 1: Trazar veredicto del LLM Juez en ArtDirectorDecision
            score_label = f"{score:.2f}" if score is not None else "n/a"
            summary = f"LLM QA Judge: score={score_label}, needs_rework={needs_rework}"
            if llm_flag_overridden:
                summary += f" (LLM flag needs_rework={llm_flag} overridden by score vs threshold)"
            self.log_decision(
                db=db,
                job_id=job_id,
                decision_type="qa_score",
                summary=summary,
                reasoning=reasoning,
                prompt_used=prompt,
                response_raw=result,
                metadata={
                    "score": score,
                    "threshold": threshold,
                    "needs_rework": needs_rework,
                    "llm_needs_rework": llm_flag,
                    "llm_flag_overridden": llm_flag_overridden,
                },
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
