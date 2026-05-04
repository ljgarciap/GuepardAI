import os
import random
import json
import time
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from PIL import Image

# --- DYNAMIC BREATHING ENGINE (v8.35 - ADAPTIVE SPACING) ---

def hex_to_rgb(hex_str: str) -> RGBColor:
    if not hex_str or not isinstance(hex_str, str): return RGBColor(0, 82, 163)
    h = hex_str.lstrip('#')
    if len(h) < 6: h = "0052A3"
    try:
        return RGBColor(*tuple(int(h[i:i+2], 16) for i in (0, 2, 4)))
    except:
        return RGBColor(0, 82, 163)

def get_luminance(rgb):
    return (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255

def get_contrast_text_color(bg_rgb):
    return RGBColor(255, 255, 255) if get_luminance(bg_rgb) < 0.5 else RGBColor(20, 20, 20)

class GammaPainter:
    def __init__(self, brand_style):
        print(f"  [Painter] --- DYNAMIC BREATHING v8.35 ---")
        self.brand = brand_style
        self.primary = hex_to_rgb(brand_style.primary_color)
        self.secondary = hex_to_rgb(brand_style.secondary_color)
        self.bg = hex_to_rgb(brand_style.background_color or "#FFFFFF")
        self.main_font = getattr(brand_style, "font_family", "Arial") or "Arial"
        
        # RIGID ANCHORS (%)
        self.LOGO_X = 90.0
        self.LOGO_Y = 3.5
        self.LOGO_W = 9.0
        
        self.TITLE_X = 53.0
        self.TITLE_Y = 6.0
        self.TITLE_W = 34.0
        
        self.SAFE_BOTTOM = 92.0
        
        bg_lum = get_luminance(self.bg)
        p_lum = get_luminance(self.primary)
        self.title_color = self.primary if abs(bg_lum - p_lum) > 0.35 else get_contrast_text_color(self.bg)

        self.prs = Presentation()
        self.prs.slide_width = Inches(13.33)
        self.prs.slide_height = Inches(7.5)
        self.blank_layout = self.prs.slide_layouts[6]

    def w(self, pct): return self.prs.slide_width * (pct / 100.0)
    def h(self, pct): return self.prs.slide_height * (pct / 100.0)

    def resolve_image(self, asset_file, min_res=300):
        if not asset_file: return None
        candidates = []
        if os.path.isabs(asset_file): candidates.append(asset_file)
        filename = os.path.basename(asset_file)
        candidates.extend([os.path.abspath(os.path.join("uploads", filename)), os.path.abspath(os.path.join("backend", "uploads", filename))])
        for target in candidates:
            if os.path.exists(target): return target
        return None

    def add_rect(self, slide, x, y, w, h, color, alpha=0, rounded=False):
        shape = slide.shapes.add_shape(5 if rounded else 1, x, y, w, h)
        shape.fill.solid()
        shape.fill.fore_color.rgb = color
        if alpha > 0: shape.fill.transparency = alpha 
        shape.line.fill.background()
        return shape

    def add_text(self, slide, text, x, y, w, h, size=24, color=None, bold=False, align=PP_ALIGN.LEFT):
        tx = slide.shapes.add_textbox(x, y, w, h)
        tf = tx.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = str(text)
        p.alignment = align
        p.font.name = self.main_font
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.color.rgb = color or get_contrast_text_color(self.bg)
        return tx

    def add_fitted_image(self, slide, img_path, x, y, max_w, max_h):
        try:
            with Image.open(img_path) as img:
                orig_w, orig_h = img.size
                ratio = min(max_w / orig_w, max_h / orig_h)
                new_w = orig_w * ratio
                new_h = orig_h * ratio
                off_x = max_w - new_w
                off_y = (max_h - new_h) / 2
                slide.shapes.add_picture(img_path, x + off_x, y + off_y, width=new_w, height=new_h)
        except: pass

    def render_slides(self, content_json):
        slides = content_json.get("slides", [])
        logo_path = content_json.get("logo_path")
        for slide_data in slides:
            layout = slide_data.get("layout_type", "composition_hero")
            if layout == "composition_split": slide = self.paint_split(slide_data)
            elif layout == "big_metric": slide = self.paint_big_metric(slide_data)
            elif layout == "composition_grid": slide = self.paint_grid(slide_data)
            elif layout == "composition_quote": slide = self.paint_quote(slide_data)
            else: slide = self.paint_hero(slide_data)
            
            if logo_path:
                res = self.resolve_image(logo_path, 10)
                if res:
                    self.add_fitted_image(slide, res, self.w(self.LOGO_X), self.h(self.LOGO_Y), self.w(self.LOGO_W), self.h(8))

    def paint_split(self, slide_data):
        slide = self.secure_slide()
        img = self.resolve_image(slide_data.get("primary_asset_path"), 300)
        if img:
            self.add_fitted_image(slide, img, 0, 0, self.w(50), self.prs.slide_height)
        else:
            fb = blend_colors(self.secondary, self.bg, 0.1)
            self.add_rect(slide, 0, 0, self.w(50), self.prs.slide_height, fb)
            
        self.add_rect(slide, self.w(50), 0, self.w(50), self.prs.slide_height, self.bg)
        
        title = slide_data.get("title", "")
        # v8.35: DYNAMIC CALCULATIONS
        approx_lines = (len(title) // 32) + 1
        t_size = 28 if approx_lines == 1 else 24
        content_top = 26.0 + (approx_lines * 4.5)
        
        self.add_text(slide, title, self.w(self.TITLE_X), self.h(self.TITLE_Y), self.w(self.TITLE_W), self.h(20), size=t_size, bold=True, color=self.title_color)
        
        bullets = slide_data.get("bullets", [])
        num_b = len(bullets[:5])
        available_h = self.SAFE_BOTTOM - content_top
        row_h = min(10.0, available_h / max(1, num_b))
        
        for idx, b in enumerate(bullets[:5]):
            y_pct = content_top + (idx * row_h)
            self.add_rect(slide, self.w(53), self.h(y_pct), Pt(18), Pt(18), self.primary, rounded=True)
            self.add_text(slide, b, self.w(56), self.h(y_pct), self.w(40), self.h(row_h - 1), size=13, color=get_contrast_text_color(self.bg))
        return slide

    def paint_hero(self, slide_data):
        slide = self.secure_slide()
        self.add_rect(slide, 0, 0, self.prs.slide_width, self.prs.slide_height, self.primary)
        self.add_text(slide, slide_data.get("title", ""), self.w(10), self.h(30), self.w(80), self.h(40), size=48, bold=True, color=get_contrast_text_color(self.primary), align=PP_ALIGN.CENTER)
        return slide

    def paint_grid(self, slide_data):
        slide = self.secure_slide()
        self.add_rect(slide, 0, 0, self.prs.slide_width, self.prs.slide_height, self.bg)
        self.add_text(slide, slide_data.get("title", ""), self.w(7), self.h(6), self.w(86), self.h(15), size=34, bold=True, color=self.title_color)
        bullets = slide_data.get("bullets", [])
        for idx, b in enumerate(bullets[:4]):
            x_pct = 7 + (idx * 23)
            self.add_rect(slide, self.w(x_pct), self.h(30), self.w(21), self.h(58), self.secondary, alpha=0.05, rounded=True)
            self.add_text(slide, b, self.w(x_pct + 1), self.h(32), self.w(19), self.h(54), size=14)
        return slide

    def paint_big_metric(self, slide_data):
        slide = self.secure_slide()
        self.add_rect(slide, 0, 0, self.prs.slide_width, self.prs.slide_height, self.bg)
        self.add_text(slide, slide_data.get("metric", ""), 0, self.h(40), self.prs.slide_width, self.h(30), size=140, bold=True, color=self.primary, align=PP_ALIGN.CENTER)
        return slide

    def paint_quote(self, slide_data):
        slide = self.secure_slide()
        self.add_rect(slide, 0, 0, self.prs.slide_width, self.prs.slide_height, self.primary)
        q = slide_data.get("bullets", [""])[0] or slide_data.get("title", "")
        self.add_text(slide, f"\"{q}\"", self.w(15), self.h(30), self.w(70), self.h(50), size=44, bold=True, color=get_contrast_text_color(self.primary), align=PP_ALIGN.CENTER)
        return slide

    def secure_slide(self):
        slide = self.prs.slides.add_slide(self.blank_layout)
        for shape in list(slide.placeholders):
            sp = shape.element
            sp.getparent().remove(sp)
        return slide

    def save(self, path):
        self.prs.save(path)
        return path

def blend_colors(c1_rgb, c2_rgb, ratio):
    return RGBColor(int(c1_rgb[0] * ratio + c2_rgb[0] * (1 - ratio)), int(c1_rgb[1] * ratio + c2_rgb[1] * (1 - ratio)), int(c1_rgb[2] * ratio + c2_rgb[2] * (1 - ratio)))
