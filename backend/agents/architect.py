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
                job.status = models.GenerationJobStatus.PLANNING_DESIGN
                job.current_step = "Agent: Architect is assigning layouts and images..."
                db.commit()

            # Llama a la lógica original de dirección de arte
            success = plan_presentation_design(db, job_id, is_premium=is_premium)

            if success and is_premium and job:
                # Run premium art director enrichment
                from services.generation.decoupled_art_director import PremiumArtDirector
                from schemas.presentation import ContentManifest, ContentManifestSlide, DesignManifest, DesignManifestSlide
                import os

                # Retrieve design system
                dna = db.query(models.BrandVisualDna).filter(models.BrandVisualDna.brand_id == job.brand_id).order_by(models.BrandVisualDna.created_at.desc()).first()
                design_system = {
                    "primary_color": getattr(dna, "primary_color", "#0052A3"),
                    "secondary_color": getattr(dna, "secondary_color", "#EE1C2E"),
                    "background_color": getattr(dna, "background_color", "#FFFFFF"),
                }

                # Retrieve content manifest
                slides_list = []
                saved_slides = db.query(models.PresentationSlide).filter(models.PresentationSlide.job_id == job_id).order_by(models.PresentationSlide.slide_number.asc()).all()
                for s in saved_slides:
                    cjson = s.content_json or {}
                    raw_bullets = cjson.get("bullets", [])
                    safe_bullets = [b.get("description", b.get("priority", str(b))) if isinstance(b, dict) else str(b) for b in raw_bullets]
                    slides_list.append(ContentManifestSlide(
                        slide_number=s.slide_number,
                        title=s.title,
                        subtitle=cjson.get("subtitle"),
                        bullets=safe_bullets,
                        metrics=cjson.get("metrics", []),
                        metric=cjson.get("metric"),
                        label=cjson.get("label"),
                        layout_type=cjson.get("layout_type", "strategic_split"),
                        section_label=cjson.get("section_label"),
                        metadata=cjson.get("metadata", {}),
                        planning_json=s.planning_json or {}
                    ))
                content_manifest = ContentManifest(job_id=job_id, slides=slides_list)

                # Retrieve design manifest
                d_slides = []
                for s in saved_slides:
                    primary_path = None
                    img_val = s.assigned_image
                    if img_val:
                        if str(img_val).isdigit():
                            asset_rec = db.query(models.BrandAsset).get(int(img_val))
                            if asset_rec and asset_rec.local_path:
                                primary_path = asset_rec.local_path
                        else:
                            primary_path = str(img_val)

                    d_slides.append(DesignManifestSlide(
                        slide_number=s.slide_number,
                        layout_type=s.layout_slug or s.content_json.get("layout_type", "strategic_split"),
                        primary_asset_path=primary_path
                    ))
                base_manifest = DesignManifest(job_id=job_id, slides=d_slides, theme={})

                uploads_dir = os.path.abspath("uploads")
                if not os.path.exists(uploads_dir):
                    uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))

                art_director = PremiumArtDirector(db, job_id, uploads_dir)
                final_design = art_director.enrich_design(base_manifest, content_manifest, design_system)

                # Persist the generated background_asset_path back to the db presentation slides
                for d_slide in final_design.slides:
                    slide_rec = next((s for s in saved_slides if s.slide_number == d_slide.slide_number), None)
                    if slide_rec:
                        slide_rec.background_asset_path = d_slide.background_asset_path
                db.commit()

            if job and success:
                job.status = models.GenerationJobStatus.DESIGN_PLANNED
                job.current_step = "Layout and images successfully assigned."
                db.commit()

            # GAP 1: Trazar decisión de layout por slide en ArtDirectorDecision
            if success:
                planned_slides = db.query(models.PresentationSlide).filter(
                    models.PresentationSlide.job_id == job_id,
                    models.PresentationSlide.status == models.PresentationSlideStatus.PLANNED
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
