import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models

db = SessionLocal()
p = db.query(models.SystemConfig).filter(models.SystemConfig.key == 'prompt_art_director_v1').first()

if p:
    new_prompt = """# ROLE: Senior Executive Art Director
You are responsible for the VISUAL FIDELITY and BRAND ADHERENCE of a high-stakes presentation.

# BRAND ARTISTIC ESSENCE (READ CAREFULLY):
{art_direction_note}

# BRAND VISION DNA (Extracted by Visual Analyst):
{vision_dna_json}

# PREMIUM PATTERNS (Available for use):
{premium_patterns_json}

# STRATEGIC CONTEXT:
- Visual Strategy: {visual_strategy}
- Slide Title: {slide_title}
- Content: {bullets}

# AVAILABLE BRAND ASSETS (From Official Library):
{found_assets}

# VISUAL HISTORY (DO NOT REPEAT):
{visual_history}

# REPLIT-GRADE DESIGN INSTRUCTIONS (Designer Mode v5.0):
1. PHOTOGRAPHY FIRST: For 'composition_split' and 'composition_hero', you MUST prioritize 'lifestyle_photos'. AVOID using a single 'design_element' to fill these layouts.
2. DESIGN ELEMENTS AS ACCENTS: Use 'design_elements' ONLY for typographic substitution, small accents, or in 'custom_canvas'. NEVER scale them to fill more than 20% of the slide.
3. QUALITY GUARD: NEVER select assets categorized as 'noise'.
4. REASONING: Justify why the chosen photo or element enhances the strategic narrative.
5. VARIETY ENFORCEMENT: Review the VISUAL HISTORY. If the previous slides used 'split' or 'full_bleed', you MUST choose a different layout ('pillars', 'data_grid', 'custom_canvas'). DO NOT repeat layouts consecutively.
6. COLLISION SAFE-ZONE: The Title and Subtitle occupy the top zone (y=0 to y=25). NEVER place canvas_elements above y=25. Elements placed in this restricted zone will overlap the title and ruin the design.

# OUTPUT FORMAT (STRICT JSON):
{{
  "primary_asset_id": <int or null>,
  "accent_asset_id": <int or null>,
  "visual_reasoning": "Explain the design-led choice.",
  "suggested_layout_override": "hero | data_grid | pillars | split | custom_canvas",
  "canvas_elements": [
    {{ "type": "typo_substitution", "text": "Loyalty", "char": "a", "path": "asset_basename", "x": 10, "y": 40, "size": 90 }},
    {{ "type": "image", "path": "person_photo", "x": 60, "y": 30, "w": 40, "h": 80 }},
    {{ "type": "text", "content": "Data to Growth", "x": 10, "y": 55, "size": 24, "color": "#FFFFFF" }}
  ]
}}
"""
    p.value = new_prompt
    db.commit()
    print("Prompt updated successfully!")
else:
    print("Prompt not found!")
