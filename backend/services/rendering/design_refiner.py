"""
design_refiner.py — PowerAI
El "Director de Arte" que audita y pule el manifiesto de diseño antes del renderizado final.
Cruce inteligente entre contenido, matemáticas y ADN de marca.
"""
import json
from typing import List
from providers.llm_provider import generate_json

REFINER_PROMPT = """
You are a World-Class Art Director and Graphic Designer. 
Your mission is to transform a math-based layout manifest into a brand-faithful masterpiece.

BRAND ESSENCE (Extracted from actual brand identity documents):
{brand_essence_json}

INSTRUCTIONS:
1. FIDELITY: Apply ONLY the design gestures, structural archetypes, and patterns described in the BRAND ESSENCE above.
2. LAYOUT PRESERVATION: [CRITICAL] Do NOT change the "layout" field of any slide's archetype. The layout structure (e.g., split-left, full-bleed) was decided by a deterministic engine and MUST be preserved.
3. REFINEMENT: You may ONLY adjust: coordinates (fine-tuning), font sizes, colors, shape geometries, and opacity values within the established layout.
4. GESTURES: If the brand essence specifies particular shapes (banners, pills, lines), add them to the slide shapes array.
5. NO OVERLAP: Ensure text never overlaps with the main subjects of the images described in the narrative.

INPUT MANIFEST:
{manifest_json}

Return ONLY the perfected JSON manifest.
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
