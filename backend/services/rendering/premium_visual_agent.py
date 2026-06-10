"""
Premium Visual Agent v1.

Experimental HTML/CSS renderer for pdf_artistic. It is deliberately isolated
from the python-pptx/GammaPainter flow.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import models
from services.ingestion.visual_pattern_service import (
    get_latest_brand_patterns,
    normalize_executable_patterns,
)
from services.rendering.artistic_pdf_service import artistic_pdf_service
from sqlalchemy.orm import Session


def hex_is_dark(hex_color: str) -> bool:
    if not hex_color:
        return False
    hex_color = hex_color.lstrip('#')
    try:
        if len(hex_color) == 3:
            hex_color = "".join(c * 2 for c in hex_color)
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return luminance < 0.5
    except Exception:
        return False


class PremiumVisualAgent:
    def __init__(self, db: Session, job_id: int, uploads_dir: str):
        self.db = db
        self.job_id = job_id
        self.uploads_dir = uploads_dir
        self.job = db.query(models.GenerationJob).get(job_id)

    def render_pdf(self, content_manifest, design_manifest, brand_dna) -> str:
        if not self.job:
            raise ValueError(f"Generation job {self.job_id} not found")

        patterns = self._load_patterns(brand_dna)
        brand_assets = self._load_brand_assets(getattr(brand_dna, "brand_id", None))
        
        # Iteration 1: Generate (Initial planning)
        slides_data = self._build_slides(content_manifest, design_manifest, brand_dna, patterns, brand_assets)
        preflight = self._evaluate_slides(slides_data, patterns)

        # Iteration 2: Adjust (Claude Vision API)
        print(f"  [PremiumVisualAgent] Starting Iteration 2: Vision Adjust Loop...", flush=True)
        try:
            slides_data = self._vision_adjust_loop(slides_data, patterns, brand_dna, brand_assets)
            print(f"  [PremiumVisualAgent] Vision Adjust Loop completed.", flush=True)
        except Exception as e:
            import traceback
            print(f"  [PremiumVisualAgent] Vision Adjust Loop failed, falling back to iteration 1: {traceback.format_exc()}", flush=True)

        output_path = artistic_pdf_service.generate_premium_pdf(
            self.job_id,
            slides_data,
            brand_dna=brand_dna,
            patterns=patterns,
            evaluation=preflight,
        )
        final_eval = self._record_evaluation(slides_data, patterns, preflight, output_path)
        print(f"  [PremiumVisualAgent] Evaluation: {final_eval}")
        return output_path

    def _vision_adjust_loop(self, slides_data: List[Dict[str, Any]], patterns: List[Dict[str, Any]], brand_dna, brand_assets) -> List[Dict[str, Any]]:
        """
        Calls Claude API to evaluate and adjust the layouts and visual strategy for a super professional result.
        """
        from providers.llm_provider import generate_premium_json
        import json
        
        prompt = f"""
        You are a World-Class Art Director reviewing the first iteration of a Premium Presentation.
        Your goal is to ADJUST the layout patterns and image usage to maximize visual impact and BRAND DNA fidelity.
        
        BRAND DNA:
        - Primary Color: {getattr(brand_dna, 'primary_color', '#000')}
        
        AVAILABLE BRAND PATTERNS (Extracted from Brand Manual):
        {json.dumps([{
            'pattern_type': p.get('pattern_type'),
            'description': p.get('description'),
            'execution_hint': p.get('execution_hint')
        } for p in patterns], indent=2)}
        
        CURRENT GENERATION (Iteration 1):
        {json.dumps([{'slide_number': s['slide_number'], 'title': s['title'], 'pattern_type': s['pattern_type']} for s in slides_data], indent=2)}
        
        INSTRUCTIONS:
        1. If you see repeated patterns (e.g., all "editorial_split"), break the monotony by assigning more creative patterns from the AVAILABLE BRAND PATTERNS list.
        2. Evaluate the TITLE and CONTENT of each slide. Assign the pattern that best fits the semantic meaning and the brand's visual strategy based on the pattern's description.
        3. Return an adjusted array of pattern assignments.
        
        OUTPUT JSON FORMAT:
        {{
            "adjustments": [
                {{
                    "slide_number": 1,
                    "pattern_type": "full_bleed_hero",
                    "reason": "Cover slide needs maximum impact"
                }}
            ]
        }}
        """
        
        response = generate_premium_json(prompt)
        adjustments = response.get("adjustments", [])
        
        # Apply adjustments
        for adj in adjustments:
            for slide in slides_data:
                if slide["slide_number"] == adj["slide_number"]:
                    slide["pattern_type"] = adj.get("pattern_type", slide["pattern_type"])
                    break
                    
        return slides_data

    def _load_patterns(self, brand_dna) -> List[Dict[str, Any]]:
        brand_id = getattr(brand_dna, "brand_id", None)
        patterns = get_latest_brand_patterns(self.db, brand_id)
        if patterns:
            return patterns

        essence = (
            self.db.query(models.BrandArtisticEssence)
            .filter(models.BrandArtisticEssence.brand_id == brand_id)
            .order_by(models.BrandArtisticEssence.updated_at.desc())
            .first()
        )
        if not essence:
            return normalize_executable_patterns({})

        essence_payload = {
            "visual_strategy": essence.visual_strategy,
            "structural_archetypes": essence.structural_archetypes,
            "design_gestures": essence.design_gestures,
            "composition_rules": essence.composition_rules,
            "slide_archetypes": essence.slide_archetypes,
        }
        raw_payload = essence.raw_vision_response or {}
        if raw_payload.get("executable_visual_patterns"):
            return normalize_executable_patterns(raw_payload)
        return normalize_executable_patterns(essence_payload)

    def _load_brand_assets(self, brand_id: Optional[int]) -> Dict[str, List[models.BrandAsset]]:
        assets_by_category: Dict[str, List[models.BrandAsset]] = {}
        if not brand_id:
            return assets_by_category

        assets = (
            self.db.query(models.BrandAsset)
            .filter(models.BrandAsset.brand_id == brand_id)
            .order_by(models.BrandAsset.created_at.desc())
            .all()
        )
        for asset in assets:
            assets_by_category.setdefault(asset.category or "unknown", []).append(asset)
        return assets_by_category

    def _build_slides(self, content_manifest, design_manifest, brand_dna, patterns, brand_assets) -> List[Dict[str, Any]]:
        # Get footer configuration
        is_enabled_config = self.db.query(models.SystemConfig).filter(models.SystemConfig.key == "is_footer_enabled").first()
        is_footer_enabled = (is_enabled_config.value == "true") if is_enabled_config else True
        
        active_footer = self.db.query(models.FooterConfig).filter(
            models.FooterConfig.is_selected == True,
            models.FooterConfig.is_active == True
        ).first()

        footer_text = ""
        footer_disclaimer = ""
        footer_logo_light = None
        footer_logo_dark = None
        
        brand = self.db.query(models.Brand).get(getattr(brand_dna, "brand_id", 0)) if brand_dna else None
        brand_name = brand.name if brand else "TESCO"

        if is_footer_enabled:
            if active_footer:
                footer_text = active_footer.text or "L - founders of loyalty"
                disclaimer_val = active_footer.disclaimer or ""
                disclaimer_val = disclaimer_val.replace("{brand}", brand_name.upper()).replace("{Brand}", brand_name.upper()).replace("{BRAND}", brand_name.upper())
                footer_disclaimer = disclaimer_val
                footer_logo_light = active_footer.logo_light_path
                footer_logo_dark = active_footer.logo_dark_path
            else:
                footer_text = "L - founders of loyalty"
                footer_disclaimer = f"CONFIDENTIAL FOR {brand_name.upper()} USE ONLY"

        # Dossier logo (official logo)
        brand_logo_dossier = self._asset_path(models.BrandAsset(local_path=brand.logo_path)) if brand and brand.logo_path else None
        
        # Fetch brand logos for fallback
        brand_logos = self.db.query(models.BrandAsset).filter(
            models.BrandAsset.brand_id == getattr(brand_dna, "brand_id", 0),
            models.BrandAsset.category == "logos"
        ).all()
        
        # Filter logos to only contain the brand name to avoid picking other brands or agency logos
        brand_name_lower = brand_name.lower()
        matching_logos = [
            asset for asset in brand_logos
            if brand_name_lower in asset.local_path.lower() or brand_name_lower in (asset.description or "").lower()
        ]
        logo_candidates = matching_logos if matching_logos else brand_logos
        
        brand_logo_light_path = None
        brand_logo_dark_path = brand_logo_dossier
        
        for asset in logo_candidates:
            path_lower = asset.local_path.lower()
            desc_lower = (asset.description or "").lower()
            if any(x in path_lower or x in desc_lower for x in ["light", "white", "inverse", "negativo", "blanco"]):
                brand_logo_light_path = self._asset_path(asset)
            elif not brand_logo_dark_path:
                brand_logo_dark_path = self._asset_path(asset)
        
        # Fallbacks for brand logos
        if not brand_logo_dark_path and logo_candidates:
            brand_logo_dark_path = self._asset_path(logo_candidates[0])
        if brand_logo_dark_path and not brand_logo_light_path:
            brand_logo_light_path = brand_logo_dark_path
        if brand_logo_light_path and not brand_logo_dark_path:
            brand_logo_dark_path = brand_logo_light_path

        logo_asset = self._first_asset(brand_assets, ["logos"])
        photo_asset = self._first_asset(brand_assets, ["lifestyle_photos", "photos", "backgrounds"])

        slides_data: List[Dict[str, Any]] = []
        for index, content_slide in enumerate(content_manifest.slides):
            design_slide = design_manifest.slides[index] if index < len(design_manifest.slides) else None
            layout_type = getattr(content_slide, "layout_type", "") or ""
            pattern = self._choose_pattern(index, layout_type, patterns)
            pattern_type = pattern.get("pattern_type", "editorial_split")

            planning = getattr(content_slide, "planning_json", {}) or {}
            ad_plan = planning.get("art_director", {})
            canvas_elements = ad_plan.get("canvas_elements", [])
            
            accent_image_path = None
            if ad_plan.get("accent_asset_id"):
                for assets in brand_assets.values():
                    for a in assets:
                        if str(a.id) == str(ad_plan.get("accent_asset_id")):
                            accent_image_path = self._asset_path(a)
                            break
                    if accent_image_path:
                        break

            hero_image = (
                getattr(design_slide, "primary_asset_path", None)
                or getattr(design_slide, "background_asset_path", None)
                or self._asset_path(photo_asset)
            )

            # Determine background luminance at left and right positions
            is_dark_left = False
            is_dark_right = False
            
            primary_is_dark = hex_is_dark(getattr(brand_dna, "primary_color", "#002D62"))
            
            if pattern_type == "full_bleed_hero":
                is_dark_left = True
                is_dark_right = True
            elif pattern_type == "data_cards_brand_grid":
                is_dark_left = False
                is_dark_right = False
            else: # Any split layout (editorial_split, strategic_split, composition_split, etc.)
                is_dark_left = True
                is_dark_right = False
                
            bg_asset = getattr(design_slide, "background_asset_path", None)
            if bg_asset and isinstance(bg_asset, str):
                bg_lower = bg_asset.lower()
                if any(x in bg_lower for x in ("dark", "black", "blue", "navy", "negativo", "dark_bg")):
                    is_dark_left = True
                    is_dark_right = True
            
            # Select logo light/dark for footer
            slide_footer_logo_light = footer_logo_light or brand_logo_light_path
            slide_footer_logo_dark = footer_logo_dark or brand_logo_dark_path
                
            # Select logo for header: prioritize dossier logo for brand consistency
            selected_header_logo = brand_logo_dossier
            if not selected_header_logo:
                selected_header_logo = brand_logo_light_path if is_dark_right else brand_logo_dark_path
            if not selected_header_logo:
                # Use default logo path as final fallback
                default_logo = brand.logo_path if brand and brand.logo_path else self._asset_path(logo_asset)
                selected_header_logo = default_logo

            slides_data.append({
                "slide_number": content_slide.slide_number,
                "title": content_slide.title,
                "subtitle": content_slide.subtitle,
                "bullets": content_slide.bullets or [],
                "metrics": content_slide.metrics or [],
                "metadata": content_slide.metadata or {},
                "section_label": content_slide.section_label,
                "layout_intent": layout_type,
                "pattern_type": pattern_type,
                "pattern_id": pattern.get("id"),
                "pattern_hint": pattern.get("execution_hint", ""),
                "hero_image": hero_image,
                "accent_image": accent_image_path,
                "logo_image": selected_header_logo,
                "is_footer_enabled": is_footer_enabled,
                "footer_text": footer_text,
                "footer_disclaimer": footer_disclaimer,
                "footer_logo_light": slide_footer_logo_light,
                "footer_logo_dark": slide_footer_logo_dark,
                "footer_logo": slide_footer_logo_light if is_dark_left else slide_footer_logo_dark,
                "is_dark_left": is_dark_left,
                "is_dark_right": is_dark_right,
                "canvas_elements": canvas_elements,
            })

        return slides_data

    def _choose_pattern(self, index: int, layout_type: str, patterns: List[Dict[str, Any]]) -> Dict[str, Any]:
        layout_lower = layout_type.lower()

        if index == 0:
            preferred = self._find_pattern(patterns, "full_bleed_hero")
            if preferred:
                return preferred
        if any(token in layout_lower for token in ["data", "grid", "metric"]):
            preferred = self._find_pattern(patterns, "data_cards_brand_grid")
            if preferred:
                return preferred
        if any(token in layout_lower for token in ["hero", "cover"]):
            preferred = self._find_pattern(patterns, "full_bleed_hero")
            if preferred:
                return preferred

        for pattern in sorted(patterns, key=lambda item: item.get("confidence", 0), reverse=True):
            preferred_layouts = [str(item).lower() for item in pattern.get("preferred_layouts", [])]
            if not preferred_layouts or layout_lower in preferred_layouts:
                return pattern

        return {"pattern_type": "editorial_split", "id": "fallback_editorial_split", "confidence": 0.5}

    def _find_pattern(self, patterns: List[Dict[str, Any]], pattern_type: str) -> Optional[Dict[str, Any]]:
        for pattern in patterns:
            if pattern.get("pattern_type") == pattern_type:
                return pattern
        return None

    def _first_asset(self, assets_by_category: Dict[str, List[models.BrandAsset]], categories: List[str]):
        for category in categories:
            assets = assets_by_category.get(category) or []
            if assets:
                return assets[0]
        return None

    def _asset_path(self, asset) -> Optional[str]:
        if not asset:
            return None
        path = asset.local_path
        if not path:
            return None
        if os.path.isabs(path):
            return path
        return os.path.join(self.uploads_dir, os.path.basename(path))

    def _evaluate_slides(self, slides_data: List[Dict[str, Any]], patterns: List[Dict[str, Any]]) -> Dict[str, Any]:
        evaluations = []
        for slide in slides_data:
            score = 0.45
            notes = []
            if slide.get("pattern_type"):
                score += 0.15
            else:
                notes.append("missing_pattern")
            if slide.get("hero_image") or slide.get("pattern_type") == "data_cards_brand_grid":
                score += 0.15
            else:
                notes.append("missing_visual_asset")
            if slide.get("logo_image"):
                score += 0.1
            else:
                notes.append("missing_logo_lockup")
            if slide.get("bullets") or slide.get("metrics") or slide.get("subtitle"):
                score += 0.1
            else:
                notes.append("thin_content")

            evaluations.append({
                "slide_number": slide.get("slide_number"),
                "pattern_type": slide.get("pattern_type"),
                "score": round(min(score, 1.0), 2),
                "notes": notes,
            })

        avg_score = round(sum(item["score"] for item in evaluations) / max(len(evaluations), 1), 2)
        return {
            "agent": "premium_visual_agent_v1",
            "average_score": avg_score,
            "pattern_count": len(patterns),
            "slides": evaluations,
        }

    def _record_evaluation(self, slides_data, patterns, preflight, output_path):
        decision = models.ArtDirectorDecision(
            job_id=self.job_id,
            slide_number=0,
            decision_type="premium_visual_eval",
            summary=f"Premium PDF rendered with {len(patterns)} executable patterns.",
            reasoning="Basic post-render evaluation checks pattern assignment, asset presence, logo/footer lockup, and content density.",
            metadata_json={
                "output_path": output_path,
                "evaluation": preflight,
                "patterns": patterns,
                "slide_count": len(slides_data),
            },
        )
        self.db.add(decision)
        self.db.commit()
        return preflight
