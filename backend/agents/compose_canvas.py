"""
compose_canvas.py — ComposeCanvasTool (Artistic Generation Engine v2, Phase 1).
docs/specs/artistic-generation-v2.md

Thin BaseAgentTool wrapper (mirrors agents/architect.py::ComposeLayoutTool's
own shape) around services/generation/canvas_composer_service.py, where the
actual planning logic lives — same layering convention this codebase already
uses for the v1 Art Director.
"""
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field

from agents.base import BaseAgentTool
from database import SessionLocal
import models
from services.generation.canvas_composer_service import compose_canvas_for_job


class ComposeCanvasArgs(BaseModel):
    job_id: int = Field(..., description="ID del trabajo de generación")
    qa_feedback: Optional[Union[Dict[int, str], str]] = Field(
        None, description="Rechazo del ciclo de QA anterior; Dict[slide_number, feedback]"
    )


class ComposeCanvasTool(BaseAgentTool):
    name = "compose_canvas"
    description = (
        "Artistic Generation Engine v2: diseña cada slide directamente en canvas_elements, "
        "informado por la gramática de layout minada de la marca (BrandLayoutGrammar), en vez "
        "de elegir un grammar_type de un enum fijo. Reemplaza a compose_layout solo para "
        "engine_version='v2_artistic'."
    )
    args_schema = ComposeCanvasArgs

    def run(self, job_id: int, qa_feedback=None) -> Any:
        db = SessionLocal()
        try:
            job = db.query(models.GenerationJob).get(job_id)
            if job:
                job.status = models.GenerationJobStatus.PLANNING_DESIGN
                job.current_step = "Agent: Composer (v2_artistic) is designing slides in canvas_elements space..."
                db.commit()

            feedback = qa_feedback if isinstance(qa_feedback, dict) else None
            processed = compose_canvas_for_job(db, job_id, qa_feedback=feedback)
            db.commit()
            return {"status": "success", "slides_processed": processed}
        finally:
            db.close()

    async def arun(self, **kwargs) -> Any:
        return self.run(**kwargs)
