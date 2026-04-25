"""
design_refiner.py — PowerAI
El "Director de Arte" que audita y pule el manifiesto de diseño antes del renderizado final.
Cruce inteligente entre contenido, matemáticas y ADN de marca.
"""
import json
from typing import List
from llm_provider import generate_json

REFINER_PROMPT = """
You are a World-Class Graphic Designer and Art Director. 
Your goal is to transform a "Math-Based" layout into a "High-Fidelity Brand Masterpiece".

STRATEGY FOR TESCO BRAND:
1. SPLIT-SCREEN ENFORCEMENT: If a slide has a large image (role: background or visual), you MUST use a 50/50 Split-Screen. 
   - Left side (0-50%): Text, Titles, Bullets.
   - Right side (50-100%): Images, Photos.
   - PROHIBIT OVERLAPPING: Text must NEVER be on top of the main subject of an image.

2. PILL-BANNERS (The Tesco Gesture): 
   - Wrap ALL slide titles in a "rounded_rectangle" shape.
   - Style: Use the Brand's PRIMARY or SECONDARY color. Text inside must be WHITE.
   - Geometry: Left=margin_left-1, Top=title_top-1, Width=auto (approx 40-50), Height=title_height+2.

3. GRID & ALIGNMENT:
   - Use a strict 2-column grid for the left-side content.
   - Margin Left: EXACTLY 8%.
   - Bullet Symbol: Use '■' (Square) as detected in the manual.

4. COLOR PALETTE:
   - Backgrounds MUST be White (#FFFFFF) or very light. NO DARK GREYS.
   - Text color: Use #111111 for body, WHITE for text inside pill-banners.

INPUT MANIFEST:
{manifest_json}

BRAND DNA:
{brand_essence_json}

Return ONLY the perfected JSON. Ensure every slide has a 'banner' shape for the title if it's a content slide.
"""

def refine_manifest(manifest: dict, brand_dna: dict, brand_essence: dict) -> dict:
    """
    Auditoría visual del manifiesto antes del renderizado.
    """
    try:
        # Simplificamos para el prompt
        essence_context = {
            "structural": brand_essence.get("structural_archetypes", {}),
            "gestures": brand_essence.get("design_gestures", {}),
            "colors": {
                "primary": brand_dna.get("primary_color"),
                "secondary": brand_dna.get("secondary_color")
            }
        }
        
        prompt = REFINER_PROMPT.format(
            manifest_json=json.dumps(manifest, indent=2),
            brand_essence_json=json.dumps(essence_context, indent=2)
        )
        
        refined_manifest = generate_json(prompt, specialization="general")
        
        # Validar integridad mínima
        if "slides" not in refined_manifest:
            print("  [Refiner] Response missing 'slides', using original.")
            return manifest
            
        print("  [Refiner] Design manifest successfully audited and refined by AI Art Director.")
        return refined_manifest

    except Exception as e:
        print(f"  [Refiner] Design refinement failed: {e}. Using original math.")
        return manifest
