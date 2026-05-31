import os
import json
import asyncio
import re
import base64
import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session

import models
from schemas.presentation import ContentManifest, ContentManifestSlide, DesignManifest, DesignManifestSlide, RenderElement

logger = logging.getLogger(__name__)

class BaseArtDirector:
    def __init__(self, db: Session, job_id: int, is_premium: bool = False):
        self.db = db
        self.job_id = job_id
        self.is_premium = is_premium
        
    def plan(self, content_manifest: ContentManifest) -> DesignManifest:
        from services.generation.art_director_service import plan_presentation_design
        
        # We need to run the old logic to actually pick images for the DB slides
        # If it's already run in a previous resume run, we can check if images exist, but plan_presentation_design is safe to call
        # wait, we only want to run it if it hasn't been run.
        # But for safety we just call it.
        plan_presentation_design(self.db, self.job_id, is_premium=self.is_premium)
        
        # Now read from DB to get the assigned images
        slides = []
        db_slides = self.db.query(models.PresentationSlide).filter(models.PresentationSlide.job_id == self.job_id).order_by(models.PresentationSlide.slide_number.asc()).all()
        
        for i, s in enumerate(content_manifest.slides):
            db_s = db_slides[i] if i < len(db_slides) else None
            primary_path = None
            if db_s and db_s.assigned_image:
                img_val = db_s.assigned_image
                if str(img_val).isdigit():
                    asset_rec = self.db.query(models.BrandAsset).get(int(img_val))
                    if asset_rec and asset_rec.local_path:
                        primary_path = asset_rec.local_path
                else:
                    primary_path = str(img_val)
                    
            slides.append(DesignManifestSlide(
                slide_number=s.slide_number,
                layout_type=s.layout_type,
                primary_asset_path=primary_path
            ))
            
        return DesignManifest(
            job_id=self.job_id,
            slides=slides,
            theme={}
        )

class PremiumArtDirector(BaseArtDirector):
    DESIGNER_AGENT_PROMPT = """
You are a World-Class Presentation Designer and UX Architect.
We have a strictly calculated layout engine that will place the text and content on top of your background.
Your goal is to design a GLASSMORPHISM premium layout for a 1280x720 slide.

BRAND/TEMPLATE GUIDELINES:
Use the provided Brand Design System JSON for colors and shapes.
{design_system}

SLIDE CONTEXT:
The slide is titled "{title}" and its layout structure is "{grammar_type}".
The Art Director has selected the following image for this slide: {assigned_image}

TECHNICAL REQUIREMENTS:
Instead of an SVG, you will return a JSON object describing the Glassmorphism geometry that the native PPTX engine will draw.
You must return ONLY a JSON object with this schema:
{{
  "glass_panels": [
    {{
      "x_pct": float,
      "y_pct": float,
      "w_pct": float,
      "h_pct": float,
      "color_hex": "string",
      "transparency": float,
      "rounded": boolean,
      "shadow": boolean
    }}
  ],
  "image_treatment": {{
    "style": "full_bleed",
    "x_pct": float,
    "y_pct": float,
    "w_pct": float,
    "h_pct": float
  }}
}}

Make it look PREMIUM and EXPENSIVE. Use glass panels (high transparency, rounded corners, shadows) overlaying the image.
"""
    
    def __init__(self, db: Session, job_id: int, uploads_dir: str):
        super().__init__(db, job_id, is_premium=True)
        self.uploads_dir = uploads_dir
        self.sem = asyncio.Semaphore(5)  # Restored concurrency; LLM provider will throttle locally if needed
        
    def embed_base64_images_svg(self, svg_code: str) -> str:
        def replacer(match):
            filename = match.group(1).split('/')[-1]
            filepath = os.path.join(self.uploads_dir, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    ext = filepath.split('.')[-1].lower()
                    mime = "image/jpeg" if ext in ["jpg", "jpeg"] else "image/png"
                    return f'xlink:href="data:{mime};base64,{b64}"'
                except Exception as e:
                    logger.warning(f"Failed to encode {filename}: {e}")
            return match.group(0)
        
        svg_code = re.sub(r'(?:xlink:)?href=[\"\'](?:file://.*?/)?([^\"\'/]+?\.(?:png|jpg|jpeg))[\"\']', replacer, svg_code, flags=re.IGNORECASE)
        
        # Fix padding
        def fix_padding(m):
            b64 = m.group(2).rstrip('=')
            b64 += "=" * ((4 - len(b64) % 4) % 4)
            return m.group(1) + b64 + m.group(3)
        
        return re.sub(r'(data:image/[a-zA-Z0-9]+;base64,)([a-zA-Z0-9+/=]+)([\"\'])', fix_padding, svg_code)

    async def _generate_premium_geometry(self, title: str, grammar_type: str, design_system: dict, assigned_image: str, slide_number: int) -> str:
        """
        VLM Autónomo: Llama 3.2 Vision analiza la foto y devuelve todo el JSON orgánico de diseño.
        """
        from services.rendering.vision_layout_engine import generate_autonomous_layout
        
        logger.info(f"  [PremiumArtDirector] Autonomous VLM Design for Slide {slide_number}...")
        
        geometry = await asyncio.to_thread(
            generate_autonomous_layout,
            assigned_image,
            title,
            grammar_type,
            design_system
        )
        
        if not geometry or "glass_panels" not in geometry:
            logger.warning(f"[PremiumArtDirector] VLM failed to return valid JSON. Using fallback.")
            geometry = {
                "glass_panels": [{"x_pct": 5, "y_pct": 20, "w_pct": 40, "h_pct": 60, "color_hex": "#00539F", "transparency": 0.85, "rounded": True, "shadow": True}],
                "image_treatment": {"style": "full_bleed"}
            }
        
        return json.dumps(geometry)

    def enrich_design(self, base_manifest, content_manifest, design_system) -> DesignManifest:
        async def process_slides():
            tasks = []
            for d_slide in base_manifest.slides:
                title = "Slide Title"
                for c_slide in content_manifest.slides:
                    if c_slide.slide_number == d_slide.slide_number:
                        title = c_slide.title
                        break
                        
                tasks.append(self._process_slide(d_slide, title, design_system))
                
            return await asyncio.gather(*tasks)
            
        processed_slides = asyncio.run(process_slides())
        base_manifest.slides = processed_slides
        return base_manifest
        
    async def _process_slide(self, base_design_slide, title, design_system):
        async with self.sem:
            geometry_str = await self._generate_premium_geometry(
                title=title,
                grammar_type=base_design_slide.layout_type,
                design_system=design_system,
                assigned_image=base_design_slide.primary_asset_path or "",
                slide_number=base_design_slide.slide_number
            )
            
            # Pasamos el JSON de geometría en el elemento "elements" u otro lugar
            import json
            base_design_slide.background_asset_path = geometry_str # Overload this field for now
            return base_design_slide
