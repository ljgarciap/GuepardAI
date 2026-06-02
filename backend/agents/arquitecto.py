from typing import Any, Dict, List
from pydantic import BaseModel, Field
from agents.base import BaseAgentTool

from services.generation.art_director_service import plan_presentation_design
from services.ingestion.brand_composition_dna import GRAMMAR_GEOMETRIES, SLUG_ALIASES
from database import SessionLocal
import models

class GetSlideTypesArgs(BaseModel):
    pass

class GetSlideTypesTool(BaseAgentTool):
    name = "get_slide_types"
    description = "Retorna la lista de tipos de diapositivas (grammar types) disponibles en el motor de diseño."
    args_schema = GetSlideTypesArgs

    def run(self) -> Dict[str, Any]:
        """
        Retorna las geometrías disponibles y sus alias.
        """
        return {
            "available_layouts": list(GRAMMAR_GEOMETRIES.keys()),
            "aliases": SLUG_ALIASES
        }

    async def arun(self, **kwargs) -> Any:
        return self.run(**kwargs)


class ComposeLayoutArgs(BaseModel):
    job_id: int = Field(..., description="ID del trabajo de generación")
    is_premium: bool = Field(False, description="Si es True, aplica lógica de diseño avanzada (Premium/Glassmorphism)")

class ComposeLayoutTool(BaseAgentTool):
    name = "compose_layout"
    description = "Aplica la dirección de arte a las diapositivas generadas: selecciona el layout, asigna imágenes de la librería y guarda el estado 'planned' en la BD."
    args_schema = ComposeLayoutArgs

    def run(self, job_id: int, is_premium: bool = False) -> Any:
        """
        Ejecuta el plan de diseño del director de arte.
        """
        db = SessionLocal()
        try:
            job = db.query(models.GenerationJob).get(job_id)
            if job:
                job.status = "planning_design"
                job.current_step = "Agent: Arquitecto is assigning layouts and images..."
                db.commit()

            # Llama a la lógica original de dirección de arte
            success = plan_presentation_design(db, job_id, is_premium=is_premium)

            if job and success:
                job.status = "design_planned"
                job.current_step = "Layout and images successfully assigned."
                db.commit()

            # GAP 1: Trazar decisión de layout por slide en ArtDirectorDecision
            if success:
                planned_slides = db.query(models.PresentationSlide).filter(
                    models.PresentationSlide.job_id == job_id,
                    models.PresentationSlide.status == "planned"
                ).all()
                for slide in planned_slides:
                    art_reasoning = ""
                    if slide.planning_json:
                        art_reasoning = slide.planning_json.get("art_director", {}).get("reasoning", "")
                    self.log_decision(
                        db=db,
                        job_id=job_id,
                        decision_type="layout",
                        summary=f"Slide {slide.slide_number}: layout='{slide.layout_slug}', image='{slide.assigned_image}'",
                        reasoning=art_reasoning,
                        slide_number=slide.slide_number,
                        metadata={
                            "layout_slug": slide.layout_slug,
                            "assigned_image": slide.assigned_image,
                            "is_premium": is_premium,
                        },
                    )
                db.commit()

            return {"success": success, "job_id": job_id}
        finally:
            db.close()

    async def arun(self, **kwargs) -> Any:
        return self.run(**kwargs)
