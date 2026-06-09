import os
import time
from typing import Any, Dict
from pydantic import BaseModel, Field
from agents.base import BaseAgentTool

from database import SessionLocal
import models
from schemas.presentation import RenderManifest, PainterSlideData, PainterAgencyBranding, PainterFooterConfig
from services.rendering.painter import GammaPainter
from services.rendering.painter_bridge import GRAMMAR_TO_PAINTER


def normalize_bullets(bullets_list) -> list[str]:
    if not bullets_list:
        return []
    normalized = []
    for b in bullets_list:
        if isinstance(b, dict):
            val = " - ".join(str(v) for v in b.values() if v)
            normalized.append(val)
        else:
            normalized.append(str(b))
    return normalized


class RenderPPTXArgs(BaseModel):
    job_id: int = Field(..., description="ID del trabajo a renderizar")
    output_format: str = Field("pptx", description="Formato de salida (pptx o pdf_artistic)")
    is_premium: bool = Field(False, description="Si es modo Premium SVG")

class RenderPPTXTool(BaseAgentTool):
    name = "render_pptx"
    description = "Convierte el manifiesto planeado y auditado en un archivo físico (.pptx o .pdf) usando GammaPainter u otro Render Engine."
    args_schema = RenderPPTXArgs

    def run(self, job_id: int, output_format: str = "pptx", is_premium: bool = False) -> Dict[str, Any]:
        """
        Ejecuta el renderizado final basado puramente en la BD.
        """
        db = SessionLocal()
        try:
            job = db.query(models.GenerationJob).get(job_id)
            if not job:
                return {"error": "Job not found"}

            job.current_step = "Phase 3/3: Assembling native decoupled presentation..."
            job.progress = 80
            db.commit()

            dna = db.query(models.BrandVisualDna).filter(models.BrandVisualDna.brand_id == job.brand_id).order_by(models.BrandVisualDna.created_at.desc()).first()
            
            uploads_dir = os.path.abspath("uploads")
            if not os.path.exists(uploads_dir):
                uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))

            # 1. Recuperar los slides planeados
            saved_slides = db.query(models.PresentationSlide).filter(
                models.PresentationSlide.job_id == job_id
            ).order_by(models.PresentationSlide.slide_number.asc()).all()

            # 2. Manejo PDF Artístico
            if output_format == "pdf_artistic":
                # Lógica simplificada basada en el engine anterior
                if is_premium:
                    from services.rendering.premium_visual_agent import PremiumVisualAgent
                    from schemas.presentation import ContentManifest, ContentManifestSlide, DesignManifest, DesignManifestSlide
                    premium_agent = PremiumVisualAgent(db, job_id, uploads_dir)
                    
                    # Reconstruir DTOs mínimos para el PDF
                    c_slides, d_slides = [], []
                    for s in saved_slides:
                        cjson = s.content_json or {}
                        c_slides.append(ContentManifestSlide(
                            slide_number=s.slide_number,
                            title=s.title,
                            bullets=normalize_bullets(cjson.get("bullets", [])),
                            layout_type=cjson.get("layout_type", "strategic_split"),
                            metadata=cjson.get("metadata", {})
                        ))
                        primary_path = None
                        if s.assigned_image:
                            if str(s.assigned_image).isdigit():
                                arec = db.query(models.BrandAsset).get(int(s.assigned_image))
                                if arec: primary_path = arec.local_path
                            else: primary_path = str(s.assigned_image)
                        d_slides.append(DesignManifestSlide(
                            slide_number=s.slide_number,
                            layout_type=s.layout_slug or cjson.get("layout_type", "strategic_split"),
                            primary_asset_path=primary_path,
                            background_asset_path=getattr(s, "background_asset_path", None) or (s.planning_json.get("background_asset_path") if getattr(s, "planning_json", None) else None)
                        ))
                    output_path = premium_agent.render_pdf(
                        ContentManifest(job_id=job_id, slides=c_slides), 
                        DesignManifest(job_id=job_id, slides=d_slides, theme={}), 
                        dna
                    )
                else:
                    from services.rendering.artistic_pdf_service import artistic_pdf_service
                    slides_data = []
                    for s in saved_slides:
                        cjson = s.content_json or {}
                        primary_path = None
                        if s.assigned_image:
                            if str(s.assigned_image).isdigit():
                                arec = db.query(models.BrandAsset).get(int(s.assigned_image))
                                if arec: primary_path = arec.local_path
                            else: primary_path = str(s.assigned_image)
                            
                        slides_data.append({
                            "title": s.title,
                            "bullets": cjson.get("bullets", []),
                            "background_color": dna.primary_color if hasattr(dna, 'primary_color') else "#002D62",
                            "text_color": "#FFFFFF",
                            "primary_image": primary_path,
                            "layout": cjson.get("layout_type", "strategic_split"),
                            "metadata": cjson.get("metadata", {})
                        })
                    output_path = artistic_pdf_service.generate_pdf(job_id, slides_data, dna)

                job.pptx_path = output_path
                job.status = models.GenerationJobStatus.COMPLETED
                job.current_step = "Portfolio ready."
                job.progress = 100
                db.commit()
                return {"success": True, "path": output_path}

            # 3. Construir RenderManifest (PPTX)
            agency_name_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "agency_name").first()
            agency_name = agency_name_cfg.value if agency_name_cfg else "L-Founders"
            
            brand_name = "TESCO"
            if job.brand_id:
                brand_obj = db.query(models.Brand).get(job.brand_id)
                if brand_obj:
                    brand_name = brand_obj.name

            # Query all logos for the brand to classify light/dark versions
            brand_logos = db.query(models.BrandAsset).filter(
                models.BrandAsset.brand_id == job.brand_id,
                models.BrandAsset.category == "logos"
            ).all()
            
            brand_logo_dossier = os.path.basename(brand_obj.logo_path) if brand_obj and brand_obj.logo_path else None
            
            brand_logo_path = None
            brand_logo_light_path = None
            brand_logo_dark_path = brand_logo_dossier
            
            # Filter logos to only contain the brand name to avoid picking other brands or agency logos
            brand_name_lower = brand_name.lower()
            matching_logos = [
                asset for asset in brand_logos
                if brand_name_lower in asset.local_path.lower() or brand_name_lower in (asset.description or "").lower()
            ]
            logo_candidates = matching_logos if matching_logos else brand_logos
            
            for asset in logo_candidates:
                path_lower = asset.local_path.lower()
                desc_lower = (asset.description or "").lower()
                if any(x in path_lower or x in desc_lower for x in ["light", "white", "inverse", "negativo", "blanco"]):
                    brand_logo_light_path = os.path.basename(asset.local_path)
                elif not brand_logo_dark_path:
                    brand_logo_dark_path = os.path.basename(asset.local_path)
            
            # Fallbacks
            if not brand_logo_dark_path and logo_candidates:
                brand_logo_dark_path = os.path.basename(logo_candidates[0].local_path)
            if brand_logo_dark_path and not brand_logo_light_path:
                brand_logo_light_path = brand_logo_dark_path
            if brand_logo_light_path and not brand_logo_dark_path:
                brand_logo_dark_path = brand_logo_light_path
            
            brand_logo_path = brand_logo_dark_path
            
            agency_branding = PainterAgencyBranding(
                name=agency_name, logo_path=brand_logo_path,
                client_name=brand_name, email="partners@l-founders.com"
            )

            # Obtener configuración de footer activa
            is_enabled_config = db.query(models.SystemConfig).filter(models.SystemConfig.key == "is_footer_enabled").first()
            is_footer_enabled = (is_enabled_config.value == "true") if is_enabled_config else True

            active_footer = db.query(models.FooterConfig).filter(
                models.FooterConfig.is_selected == True,
                models.FooterConfig.is_active == True
            ).first()

            footer_dto = None
            if active_footer:
                disclaimer_val = active_footer.disclaimer or ""
                if "{brand}" in disclaimer_val:
                    disclaimer_val = disclaimer_val.replace("{brand}", brand_name.upper())
                
                footer_dto = PainterFooterConfig(
                    name=active_footer.name,
                    logo_light_path=active_footer.logo_light_path,
                    logo_dark_path=active_footer.logo_dark_path,
                    text=active_footer.text,
                    disclaimer=disclaimer_val,
                    is_active=active_footer.is_active,
                    is_selected=active_footer.is_selected
                )
            
            render_slides = []
            for i, s in enumerate(saved_slides):
                cjson = s.content_json or {}
                layout_type = s.layout_slug or cjson.get("layout_type", "strategic_split")
                p_layout = GRAMMAR_TO_PAINTER.get(layout_type, "composition_split")
                
                primary_path = None
                if s.assigned_image:
                    if str(s.assigned_image).isdigit():
                        arec = db.query(models.BrandAsset).get(int(s.assigned_image))
                        if arec: primary_path = arec.local_path
                    else: primary_path = str(s.assigned_image)

                render_slides.append(PainterSlideData(
                    slide_number=s.slide_number,
                    layout_type=p_layout,
                    title=s.title,
                    bullets=normalize_bullets(cjson.get("bullets", [])),
                    metrics=cjson.get("metrics", []),
                    metric=cjson.get("metric"),
                    label=cjson.get("label"),
                    tag=cjson.get("section_label") or "STRATEGY",
                    primary_asset_path=primary_path,
                    background_asset_path=getattr(s, "background_asset_path", None) or (s.planning_json.get("background_asset_path") if getattr(s, "planning_json", None) else None), # geometry JSON or path
                    is_last=(i == len(saved_slides) - 1),
                    logo_path=brand_logo_path,
                    agency_branding=agency_branding,
                    metadata=cjson.get("metadata", {}),
                    elements=[]
                ))
                
            render_manifest = RenderManifest(
                slides=render_slides,
                logo_path=brand_logo_path,
                logo_light_path=brand_logo_light_path,
                logo_dark_path=brand_logo_dark_path,
                agency_branding=agency_branding,
                is_footer_enabled=is_footer_enabled,
                footer_config=footer_dto
            )
            
            output_filename = f"Portfolio_Agent_{'Premium' if is_premium else 'Free'}_{job_id}_{int(time.time())}.pptx"
            output_path = os.path.join(uploads_dir, output_filename)
            
            painter = GammaPainter(dna)
            painter.render_slides(render_manifest)
            painter.save(output_path)
            
            job.pptx_path = output_path
            job.status = models.GenerationJobStatus.COMPLETED
            job.current_step = "Portfolio ready."
            job.progress = 100

            # GAP 1: Trazar render final en ArtDirectorDecision
            self.log_decision(
                db=db,
                job_id=job_id,
                decision_type="render",
                summary=f"Render completed: {len(render_slides)} slide(s) → {output_format.upper()}",
                reasoning=f"Output saved at: {output_path}",
                metadata={
                    "output_format": output_format,
                    "output_path": output_path,
                    "slide_count": len(render_slides),
                    "is_premium": is_premium,
                },
            )
            db.commit()

            return {"success": True, "path": output_path}
            
        finally:
            db.close()

    async def arun(self, **kwargs) -> Any:
        return self.run(**kwargs)
