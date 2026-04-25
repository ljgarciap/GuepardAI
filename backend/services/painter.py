import os
import random
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from PIL import Image

# --- INTELLIGENT DESIGN PAINTER (v9.0) ---
# Native PPTX Overhaul: No CSS Faking, High Contrast, Extractive Image Banks.
# With Architectural Image Validation & Aspect Ratio Math

def hex_to_rgb(hex_str: str) -> RGBColor:
    if not hex_str or not isinstance(hex_str, str): return RGBColor(128, 128, 128)
    h = hex_str.lstrip('#')
    if len(h) < 6: h = "808080"
    return RGBColor(*tuple(int(h[i:i+2], 16) for i in (0, 2, 4)))

def blend_colors(c1_rgb, c2_rgb, ratio):
    """Blends c1 into c2 by ratio, avoiding transparency render bugs in PPTX."""
    return RGBColor(
        int(c1_rgb[0] * ratio + c2_rgb[0] * (1 - ratio)),
        int(c1_rgb[1] * ratio + c2_rgb[1] * (1 - ratio)),
        int(c1_rgb[2] * ratio + c2_rgb[2] * (1 - ratio))
    )

class GammaPainter:
    def __init__(self, brand_style):
        self.brand = brand_style
        self.strategy = brand_style.visual_strategy or {}
        self.metrics = self.strategy.get("technical_metrics", {"kerning": -0.05, "padding_percent": 0.1})
        
        # Native High-Contrast Core
        self.primary = hex_to_rgb(brand_style.primary_color)
        self.secondary = hex_to_rgb(brand_style.secondary_color)
        
        raw_bg = brand_style.background_color or "#FFFFFF"
        self.bg = hex_to_rgb(raw_bg)
        
        # Absolute Contrast Enforcement
        r, g, b = self.bg
        self.bg_is_dark = ((0.299 * r + 0.587 * g + 0.114 * b) / 255) < 0.5
        
        self.text_on_bg = RGBColor(255, 255, 255) if self.bg_is_dark else RGBColor(20, 20, 20)
        self.text_on_primary = RGBColor(255, 255, 255) if ((0.299 * self.primary[0] + 0.587 * self.primary[1] + 0.114 * self.primary[2]) / 255) < 0.5 else RGBColor(20, 20, 20)
        self.text_on_secondary = RGBColor(255, 255, 255) if ((0.299 * self.secondary[0] + 0.587 * self.secondary[1] + 0.114 * self.secondary[2]) / 255) < 0.5 else RGBColor(20, 20, 20)

        self.main_font = brand_style.font_family or "Arial"
        
        self.prs = Presentation()
        self.prs.slide_width = Inches(13.33)
        self.prs.slide_height = Inches(7.5)
        self.blank_layout = self.prs.slide_layouts[6]
        self.title_layout = self.prs.slide_layouts[0]
        self.body_layout = self.prs.slide_layouts[1]
        
        self.asset_index = 0

        # Image Bank Engine
        self.asset_bank = []
        if self.brand.extracted_assets:
            if isinstance(self.brand.extracted_assets, str):
                try:
                    self.asset_bank = json.loads(self.brand.extracted_assets)
                except Exception:
                    pass
            elif isinstance(self.brand.extracted_assets, list):
                self.asset_bank = self.brand.extracted_assets
                
        # Shuffle deterministically based on seed
        random.seed(42)
        if self.asset_bank:
            random.shuffle(self.asset_bank)

    def secure_slide(self, layout):
        slide = self.prs.slides.add_slide(layout)
        # Nuke native ghostly placeholders to prevent "Click to add title" visual bugs
        for shape in list(slide.placeholders):
            sp = shape.element
            sp.getparent().remove(sp)
        return slide

        # Image Bank Engine
        self.asset_bank = []
        if self.brand.extracted_assets:
            # We combine logos and structural images if any exist. Some 'logos' might be photos if PDF extraction was greedy.
            for key in ['logos', 'structural_images', 'images']:
                if key in self.brand.extracted_assets:
                    self.asset_bank.extend(self.brand.extracted_assets[key])
        
        self.asset_index = 0

    def get_next_image(self, min_size=400):
        if not self.asset_bank: return None
        
        # Iteratively try up to len assets
        checked = 0
        while checked < len(self.asset_bank):
            asset_file = self.asset_bank[self.asset_index % len(self.asset_bank)]
            self.asset_index += 1
            checked += 1
            
            p1 = os.path.abspath(f"../../CreatorToolRag/backend/uploads/{asset_file}")
            p2 = os.path.abspath(f"../CreatorToolRag/backend/uploads/{asset_file}")
            
            path = p1 if os.path.exists(p1) else (p2 if os.path.exists(p2) else None)
            
            if path:
                try:
                    # Verify resolution to explicitly block blurred pixelated shapes
                    with Image.open(path) as img:
                        w, h = img.size
                        if w >= min_size and h >= min_size:
                            return path
                except Exception:
                    pass
        return None

    def col(self, n): return int((self.prs.slide_width / 12) * n)
    def row(self, n): return int((self.prs.slide_height / 12) * n)
    def w(self, n): return int((self.prs.slide_width / 12) * n)
    def h(self, n): return int((self.prs.slide_height / 12) * n)

    def add_rect(self, slide, x, y, w, h, color, alpha=0, rounded=False):
        shape_type = 5 if rounded else 1
        shape = slide.shapes.add_shape(shape_type, x, y, w, h)
        shape.fill.solid()
        shape.fill.fore_color.rgb = color
        # Revert transparency back to default PPTX expectations (0 to 1 value).
        # We handle solid colors by blending RGB instead whenever absolute solidity is needed.
        if alpha > 0: shape.fill.transparency = alpha 
        shape.line.fill.background()
        return shape

    def add_text(self, slide, text, x, y, w, h, size=24, color=None, bold=False, align=PP_ALIGN.LEFT, vertical_align=MSO_ANCHOR.TOP):
        tx = slide.shapes.add_textbox(x, y, w, h)
        tf = tx.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = vertical_align
        p = tf.paragraphs[0]
        p.text = str(text)
        p.alignment = align
        p.font.name = self.main_font
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.color.rgb = color or self.text_on_bg
        return tx

    def add_pill_label(self, slide, text, x, y):
        w_p = Pt(len(text) * 10 + 20)
        h_p = Pt(28)
        self.add_rect(slide, x, y, w_p, h_p, self.primary, rounded=True)
        self.add_text(slide, text.upper(), x, y + Pt(2), w_p, h_p, size=10, bold=True, color=self.text_on_primary, align=PP_ALIGN.CENTER, vertical_align=MSO_ANCHOR.MIDDLE)

    def render_slides(self, content_json):
        slides = content_json.get("slides", [])
        for i, slide_data in enumerate(slides):
            layout = slide_data.get("layout_type", "composition_hero")
            if i == 0 or layout == "composition_hero":
                self.paint_hero(slide_data)
            elif layout == "composition_split":
                self.paint_split(slide_data)
            elif layout == "big_metric":
                self.paint_big_metric(slide_data)
            elif layout == "composition_quote":
                self.paint_quote(slide_data)
            else:
                self.paint_grid(slide_data)

    def paint_hero(self, slide_data):
        slide = self.secure_slide(self.blank_layout)
        
        # Restore full-bleed backgrounds but preserve aspect-ratio mathematical masks
        img_path = self.get_next_image()
        if img_path:
            with Image.open(img_path) as img:
                w, h = img.size
                if (w / h) > (13.33 / 7.5):
                    # Wider than slide, bound on height
                    slide.shapes.add_picture(img_path, 0, 0, height=self.prs.slide_height)
                else:
                    # Taller than slide, bound on width
                    slide.shapes.add_picture(img_path, 0, 0, width=self.prs.slide_width)
            
            # Semi-transparent overlay mask to ensure text readability
            self.add_rect(slide, 0, 0, self.prs.slide_width, self.prs.slide_height, self.primary, alpha=0.85) # 85% transparent overlay
        else:
            self.add_rect(slide, 0, 0, self.prs.slide_width, self.prs.slide_height, self.primary)
        title = str(slide_data.get("title", "")).upper()
        
        # DNA Substitution Engine using Badges instead of breaking horizontal flow rendering
        vision_insights = self.strategy.get("vision_insights", {})
        archetypes = vision_insights.get("archetypes", [])
        badge_added = False
        
        for a in archetypes:
            if a.get("type") == "FUNCTIONAL_SUBSTITUTION":
                asset_file = a.get("asset")
                if asset_file:
                    asset_path = os.path.abspath(f"../../CreatorToolRag/backend/uploads/{asset_file}")
                    if os.path.exists(asset_path):
                        # Safely drop it as an accent floating brand mark instead of slicing title string
                        slide.shapes.add_picture(asset_path, self.prs.slide_width - Inches(2), Inches(0.5), Inches(1.2), Inches(1.2))
                        badge_added = True
                        break

        # Plot typography unmodified so it wraps naturally in PPTX bounding mechanisms
        self.add_text(slide, title, self.col(1), self.row(3), self.w(10), self.h(3), size=60, bold=True, color=self.text_on_primary)
            
        tag = slide_data.get("tag", "STRATEGY")
        self.add_pill_label(slide, tag, self.col(1), self.row(1.5))

    def paint_split(self, slide_data):
        slide = self.secure_slide(self.blank_layout)
        
        # Restore architectural geometries
        img_path = self.get_next_image()
        if img_path:
            with Image.open(img_path) as img:
                w, h = img.size
                if (w / h) > ( (13.33/2) / 7.5 ):
                    slide.shapes.add_picture(img_path, 0, 0, height=self.prs.slide_height)
                else:
                    slide.shapes.add_picture(img_path, 0, 0, width=self.col(6))
        else:
            self.add_rect(slide, 0, 0, self.col(6), self.prs.slide_height, self.secondary)
            
        # Draw solid opaque mask on right side
        self.add_rect(slide, self.col(6), 0, self.prs.slide_width - self.col(6) + Inches(1), self.prs.slide_height, self.bg)
            
        self.add_pill_label(slide, slide_data.get("tag", "CONTENT"), self.col(6.5), self.row(1))
        self.add_text(slide, slide_data.get("title", ""), self.col(6.5), self.row(2), self.w(5), self.h(1.5), size=40, bold=True, color=self.text_on_bg)
        
        bullets = slide_data.get("bullets", [])
        for idx, bullet in enumerate(bullets):
            self.add_rect(slide, self.col(6.5), self.row(4 + (idx * 1.5)), self.w(0.5), self.h(0.5), self.primary, rounded=True)
            self.add_text(slide, f"0{idx+1}", self.col(6.5), self.row(4 + (idx * 1.5)), self.w(0.5), self.h(0.5), size=12, bold=True, color=self.text_on_primary, align=PP_ALIGN.CENTER, vertical_align=MSO_ANCHOR.MIDDLE)
            self.add_text(slide, bullet, self.col(7.2), self.row(4 + (idx * 1.5)), self.w(4), self.h(1), size=18, color=self.text_on_bg)

    def paint_big_metric(self, slide_data):
        slide = self.secure_slide(self.blank_layout)
        self.add_rect(slide, 0, 0, self.prs.slide_width, self.prs.slide_height, self.bg)
        
        self.add_pill_label(slide, slide_data.get("tag", "INSIGHT"), self.col(1), self.row(1))
        self.add_text(slide, slide_data.get("title", ""), self.col(1), self.row(2), self.w(10), self.h(1.5), size=36, bold=True, color=self.text_on_bg)
        
        metric = slide_data.get("metric", "")
        self.add_text(slide, metric, self.col(1), self.row(4), self.w(10), self.h(4), size=160, bold=True, color=self.primary, align=PP_ALIGN.CENTER, vertical_align=MSO_ANCHOR.MIDDLE)
        self.add_text(slide, slide_data.get("label", ""), self.col(1), self.row(8.5), self.w(10), self.h(1.5), size=28, color=self.text_on_bg, align=PP_ALIGN.CENTER)

    def paint_quote(self, slide_data):
        slide = self.secure_slide(self.blank_layout)
        self.add_rect(slide, 0, 0, self.prs.slide_width, self.prs.slide_height, self.primary)
        
        self.add_pill_label(slide, slide_data.get("tag", "STATEMENT"), self.col(1), self.row(1))
        
        bullets = slide_data.get("bullets", [])
        quote = bullets[0] if bullets else slide_data.get("title", "")
        self.add_text(slide, f"\"{quote}\"", self.col(2), self.row(3), self.w(8), self.h(6), size=48, bold=True, color=self.text_on_primary, align=PP_ALIGN.CENTER, vertical_align=MSO_ANCHOR.MIDDLE)

    def paint_grid(self, slide_data):
        slide = self.secure_slide(self.blank_layout)
        self.add_rect(slide, 0, 0, self.prs.slide_width, self.prs.slide_height, self.bg)
        
        self.add_pill_label(slide, slide_data.get("tag", "PILLARS"), self.col(1), self.row(1))
        self.add_text(slide, slide_data.get("title", ""), self.col(1), self.row(2), self.w(10), self.h(1.5), size=40, bold=True, color=self.text_on_bg)
        
        bullets = slide_data.get("bullets", [])
        # Distribute into 2x2 or 1x3 evenly
        is_grid = len(bullets) > 3
        
        for idx, bullet in enumerate(bullets):
            if is_grid:
                c = 1 + (idx % 2) * 5.5
                r = 4.5 + (int(idx / 2) * 3)
                w = 5
            else:
                c = 1 + (idx * 3.6)
                r = 5
                w = 3.2
                
            # Create a native elegant card using Solid Blends so we circumvent pptx opacity limitations
            card_pastel = blend_colors(self.secondary, self.bg, 0.05)
            self.add_rect(slide, self.col(c), self.row(r), self.w(w), self.h(2.2), card_pastel, rounded=True)
            
            self.add_text(slide, f"{(idx+1):02d}", self.col(c) + Pt(10), self.row(r) + Pt(10), self.w(w), self.h(0.5), size=14, bold=True, color=self.primary)
            self.add_text(slide, bullet, self.col(c) + Pt(10), self.row(r) + Pt(40), self.w(w) - Pt(20), self.h(1.5), size=16, color=self.text_on_bg)

    def save(self, path):
        self.prs.save(path)
        return path
