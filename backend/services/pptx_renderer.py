import os
import re
from PIL import Image as PILImage
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_AUTO_SIZE
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
from lxml import etree

# --- UNIVERSAL GEOMETRY CONFIG ---
SLIDE_W_IN = 10.0
SLIDE_H_IN = 7.5

def scale_x(val): return Inches((val / 100.0) * SLIDE_W_IN)
def scale_y(val): return Inches((val / 100.0) * SLIDE_H_IN)

def hex_to_rgb(hex_str: str) -> RGBColor:
    if not isinstance(hex_str, str): return RGBColor(30, 30, 30)
    h = hex_str.lstrip('#')
    if len(h) == 3: h = ''.join([c*2 for c in h])
    if len(h) != 6: return RGBColor(30, 30, 30)
    try: return RGBColor(*tuple(int(h[i:i+2], 16) for i in (0, 2, 4)))
    except ValueError: return RGBColor(30, 30, 30)

def clean_text(text: str) -> str:
    if not isinstance(text, str): return str(text)
    text = re.sub(r'[*_]{1,3}', '', text)
    return text.strip()

# ──────────────────────────────────────────────
# HELPERS PARA ESTILOS AVANZADOS
# ──────────────────────────────────────────────

def set_shape_transparency(shape, opacity: float):
    """Ajusta la transparencia de un shape (0.0 a 1.0)."""
    if opacity >= 1.0: return
    
    # El valor de alpha en OOXML va de 0 a 100000
    alpha_val = int(opacity * 100000)
    
    # Acceder al XML del elemento de relleno
    sp_tree = shape._element
    solid_fill = sp_tree.find('.//' + qn('a:solidFill'))
    if solid_fill is not None:
        srgb = solid_fill.find(qn('a:srgbClr'))
        if srgb is not None:
            # Eliminar alpha existente si hay
            existing_alpha = srgb.find(qn('a:alpha'))
            if existing_alpha is not None:
                srgb.remove(existing_alpha)
            
            alpha_el = etree.SubElement(srgb, qn('a:alpha'))
            alpha_el.set('val', str(alpha_val))


def apply_corner_style(shape, style: str):
    """Ajusta el radio de las esquinas según el estilo."""
    if style == "rounded":
        # MSO_SHAPE.ROUNDED_RECTANGLE es 5
        # Podemos ajustar el radio si es necesario vía shape.adjustments
        try:
            if hasattr(shape, "adjustments") and len(shape.adjustments) > 0:
                shape.adjustments[0] = 0.05 # 5% de radio
        except: pass
    elif style == "pill":
        try:
            if hasattr(shape, "adjustments") and len(shape.adjustments) > 0:
                shape.adjustments[0] = 0.5 # Totalmente redondeado
        except: pass


# ──────────────────────────────────────────────
# ELEMENT RENDERERS
# ──────────────────────────────────────────────

def render_background_image(slide, element, asset_map):
    """
    Renderiza la imagen de fondo con estrategia 'Cover' usando CROP interno (v12.0).
    Garantiza 0 desbordamiento fuera del canvas.
    """
    img_basename = element.get("source")
    raw_path = asset_map.get(img_basename)
    
    img_path = None
    if raw_path and os.path.exists(raw_path):
        img_path = raw_path
    
    if not img_path:
        # Fallback a directorio uploads
        potential = os.path.join("uploads", str(img_basename))
        if os.path.exists(potential):
            img_path = potential

    if img_path and os.path.exists(img_path):
        try:
            # 1. Obtener dimensiones para calcular el CROP
            with PILImage.open(img_path) as img:
                iw, ih = img.size
            
            sw, sh = Inches(SLIDE_W_IN), Inches(SLIDE_H_IN)
            
            # 2. Añadir imagen ajustada al slide (0,0)
            pic = slide.shapes.add_picture(img_path, 0, 0, sw, sh)
            
            # 3. Calcular y aplicar CROP semántico (Cover strategy)
            # Queremos que la imagen llene el slide manteniendo su aspect ratio
            # r = ratio
            aspect_slide = SLIDE_W_IN / SLIDE_H_IN
            aspect_img = iw / ih
            
            if aspect_img > aspect_slide:
                # Imagen más ancha: recortar laterales
                total_crop = 1.0 - (aspect_slide / aspect_img)
                pic.crop_left = total_crop / 2
                pic.crop_right = total_crop / 2
            else:
                # Imagen más alta: recortar arriba/abajo
                total_crop = 1.0 - (aspect_img / aspect_slide)
                pic.crop_top = total_crop / 2
                pic.crop_bottom = total_crop / 2
                
            # 4. Enviar al fondo absoluto del árbol XML (Z-Order)
            # Posición 2 suele ser después de los elementos base del layout
            slide.shapes._spTree.remove(pic._element)
            slide.shapes._spTree.insert(2, pic._element)
            
        except Exception as e:
            print(f"  [Renderer] Background Image failed: {e}")
            shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, sw, sh)
            shape.fill.solid()
            shape.fill.fore_color.rgb = RGBColor(30, 30, 30)
    else:
        print(f"  [Renderer] Warning: Background asset not found for {img_basename}")


def render_shape(slide, element):
    geo = element.get("geometry", {"left": 0, "top": 0, "width": 10, "height": 10})
    style = element.get("style", {})
    
    shape_type_map = {
        "rectangle": MSO_SHAPE.RECTANGLE,
        "ellipse": MSO_SHAPE.OVAL,
        "rounded_rectangle": MSO_SHAPE.ROUNDED_RECTANGLE,
    }
    
    s_type = shape_type_map.get(element.get("shape_type", "rectangle"), MSO_SHAPE.RECTANGLE)
    if style.get("corner_style") in ["rounded", "pill"]:
        s_type = MSO_SHAPE.ROUNDED_RECTANGLE

    shape = slide.shapes.add_shape(
        s_type, 
        scale_x(geo["left"]), scale_y(geo["top"]), 
        scale_x(geo["width"]), scale_y(geo["height"])
    )
    
    shape.fill.solid()
    shape.fill.fore_color.rgb = hex_to_rgb(style.get("color", "#CCCCCC"))
    
    # Transparencia (Glassmorphism / Overlays)
    opacity = style.get("opacity", 1.0)
    set_shape_transparency(shape, opacity)
    
    # Quitar bordes por defecto
    shape.line.fill.background()
    
    # Aplicar radio de esquinas
    if s_type == MSO_SHAPE.ROUNDED_RECTANGLE:
        apply_corner_style(shape, style.get("corner_style", "rounded"))


def render_text(slide, element):
    content = clean_text(element.get("content", ""))
    if not content: return

    geo = element.get("geometry", {"left": 10, "top": 10, "width": 80, "height": 10})
    style = element.get("style", {})
    role = element.get("role", "body")
    
    tx = slide.shapes.add_textbox(
        scale_x(geo["left"]), scale_y(geo["top"]), 
        scale_x(geo["width"]), scale_y(geo["height"])
    )
    tf = tx.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    
    # --- DYNAMIC FONT SCALING (v12.1) ---
    # Si es título y es muy largo, bajamos la base para evitar colisiones
    base_size = style.get("size", 18)
    if role == "title" and len(content) > 40:
        base_size = min(base_size, 32) # Cap titles at 32pt if long
    if role == "title" and len(content) > 70:
        base_size = 24 # Extreme reduction for massive titles
        
    # Manejar múltiples párrafos
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
            
        p.text = line
        align_map = {"center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT, "left": PP_ALIGN.LEFT}
        p.alignment = align_map.get(style.get("align", "left"), PP_ALIGN.LEFT)
        
        p.font.name = style.get("font", "Arial")
        p.font.size = Pt(base_size)
        p.font.color.rgb = hex_to_rgb(style.get("color", "#000000"))
        p.font.bold = style.get("bold", role == "title")


def render_image(slide, element, asset_map):
    img_basename = element.get("source")
    geo = element.get("geometry", {"left": 0, "top": 0, "width": 20, "height": 20})
    raw_path = asset_map.get(img_basename)

    print(f"  [Renderer] Attempting to render slide asset: {img_basename}")
    print(f"  [Renderer]   - Raw path from map: {raw_path}")
    
    img_path = None
    if raw_path:
        # 1. Intentar como ruta absoluta
        if os.path.exists(raw_path):
            img_path = raw_path
            print(f"  [Renderer]   - Success: Found as absolute path.")
        # 2. Intentar como relativo a uploads
        else:
            potential = os.path.join("uploads", os.path.basename(raw_path))
            print(f"  [Renderer]   - Checking potential relative: {potential}")
            if os.path.exists(potential):
                img_path = potential
                print(f"  [Renderer]     - Success: Found in uploads/.")
            
    if not img_path:
        # 3. Intentar solo por nombre de archivo en uploads
        potential = os.path.join("uploads", str(img_basename))
        print(f"  [Renderer]   - Checking filename fallback: {potential}")
        if os.path.exists(potential):
            img_path = potential
            print(f"  [Renderer]     - Success: Found by filename.")
        # 4. Intentar en raíz del backend
        elif os.path.exists(str(img_basename)):
            img_path = str(img_basename)
            print(f"  [Renderer]     - Success: Found in root.")
    
    if not img_path:
        print(f"  [Renderer]   - CRITICAL: No file found for asset {img_basename} in any location.")

    if img_path and os.path.exists(img_path):
        try:
            # Aspect Ratio Protection (v60.0)
            with PILImage.open(img_path) as img:
                iw, ih = img.size
            
            target_w_emu = scale_x(geo["width"]).emu
            target_h_emu = scale_y(geo["height"]).emu
            
            # Fit strategy
            scale = min(target_w_emu / iw, target_h_emu / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            
            # Center within target box
            ox = scale_x(geo["left"]).emu + (target_w_emu - nw) // 2
            oy = scale_y(geo["top"]).emu + (target_h_emu - nh) // 2
            
            slide.shapes.add_picture(img_path, ox, oy, nw, nh)
            print(f"  [Renderer]   - RENDERED SUCCESSFULLY.")
        except Exception as e:
            print(f"  [Renderer]   - Error during render: {e}")


# ──────────────────────────────────────────────
# MAIN RENDERER
# ──────────────────────────────────────────────

def render_pptx_manifest(design_manifest, asset_map, output_path):
    """
    ENGINE RENDERER v16.1 — ANALYST VISION DRIVEN.
    Aplica el manifest de diseño con soporte para Canvas Ultra-Wide y Decoradores.
    """
    print(f"[Renderer v16.1] Creando presentación: {output_path}...", flush=True)
    
    # ── 1. Inicializar Canvas Dinámico ────────────────────────────────────
    canvas = design_manifest.get("canvas", {})
    slide_w_in = canvas.get("width_inches", 13.33)
    slide_h_in = canvas.get("height_inches", 7.5)
    
    prs = Presentation()
    prs.slide_width  = Inches(slide_w_in)
    prs.slide_height = Inches(slide_h_in)
    blank_layout = prs.slide_layouts[6] 
    
    theme = design_manifest.get("theme", {})
    bg_color_hex = theme.get("background", "#FFFFFF")

    # Helpers de escalado dinámico
    def sx(val): return Inches((val / 100.0) * slide_w_in)
    def sy(val): return Inches((val / 100.0) * slide_h_in)

    for slide_data in design_manifest.get("slides", []):
        slide = prs.slides.add_slide(blank_layout)
        elements = slide_data.get("elements", [])
        
        # 2. Fondo base
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = hex_to_rgb(bg_color_hex)

        # 3. Z-Order Sorting (v17.1 - Role Priority)
        # Priorizamos personas y logos al frente absoluto.
        def get_layer(el):
            etype = el.get("type")
            erole = el.get("role", "")
            if erole == "person": return 10  # Frente absoluto
            if etype == "logo": return 9
            if etype == "text": return 8
            if etype == "shape": return 2   # Bloques estructurales (Sidebar/Panels)
            if etype == "image" and erole == "background": return 0
            return 1 # Imágenes genéricas

        if elements is None: elements = []
        elements.sort(key=get_layer)

        for el in elements:
            try:
                el_type = el.get("type")
                role    = el.get("role", "")
                geo     = el.get("geometry", {})
                style   = el.get("style", {})
                
                if el_type == "image" and role == "background":
                    render_background_image_dynamic(slide, el, asset_map, slide_w_in, slide_h_in)
                elif el_type == "shape" or role in ("horizontal_bar", "vertical_bar", "footer_line", "header_zone", "brand_bar", "overlay", "sidebar_zone", "content_panel", "corner_accent", "pill_accent", "brand_dot"):
                    _render_decorator_v2(slide, el, sx, sy)
                elif el_type == "text":
                    _render_text_v2(slide, el, sx, sy)
                elif el_type in ["image", "logo"]:
                    _render_image_v2(slide, el, asset_map, sx, sy)
            except Exception as e:
                print(f"  [Renderer] Error en elemento {el.get('type')}: {e}")

    prs.save(output_path)
    print(f"[Renderer v16.1] PPTX guardado con éxito.", flush=True)
    return output_path

# ──────────────────────────────────────────────
# DYNAMIC RENDERERS v2 (v16.1)
# ──────────────────────────────────────────────

def render_background_image_dynamic(slide, element, asset_map, sw_in, sh_in):
    img_basename = element.get("source")
    img_path = asset_map.get(img_basename)
    if not (img_path and os.path.exists(img_path)):
        img_path = os.path.join("uploads", str(img_basename))
        
    if img_path and os.path.exists(img_path):
        try:
            with PILImage.open(img_path) as img: iw, ih = img.size
            pic = slide.shapes.add_picture(img_path, 0, 0, Inches(sw_in), Inches(sh_in))
            aspect_slide, aspect_img = sw_in / sh_in, iw / ih
            if aspect_img > aspect_slide:
                tc = 1.0 - (aspect_slide / aspect_img)
                pic.crop_left, pic.crop_right = tc/2, tc/2
            else:
                tc = 1.0 - (aspect_img / aspect_slide)
                pic.crop_top, pic.crop_bottom = tc/2, tc/2
            slide.shapes._spTree.remove(pic._element)
            slide.shapes._spTree.insert(2, pic._element)
        except: pass

def _render_decorator_v2(slide, element, sx, sy):
    geo, style = element.get("geometry", {}), element.get("style", {})
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, sx(geo["left"]), sy(geo["top"]), sx(geo["width"]), sy(geo["height"])
    )
    shape.line.fill.background()
    shape.fill.solid()
    shape.fill.fore_color.rgb = hex_to_rgb(style.get("color", "#CCCCCC"))
    set_shape_transparency(shape, style.get("opacity", 1.0))

def _render_text_v2(slide, element, sx, sy):
    content = clean_text(element.get("content", ""))
    if not content: return
    geo, style, role = element.get("geometry", {}), element.get("style", {}), element.get("role", "")
    tx = slide.shapes.add_textbox(sx(geo["left"]), sy(geo["top"]), sx(geo["width"]), sy(geo["height"]))
    tf = tx.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    for i, line in enumerate(content.split('\n')):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.alignment = {"center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}.get(style.get("align"), PP_ALIGN.LEFT)
        p.font.name = style.get("font", "Arial")
        p.font.size = Pt(style.get("size", 18))
        p.font.color.rgb = hex_to_rgb(style.get("color", "#000000"))
        p.font.bold = style.get("bold", role == "title")

def _render_image_v2(slide, element, asset_map, sx, sy):
    img_basename, geo, role = element.get("source"), element.get("geometry", {}), element.get("role", "")
    img_path = asset_map.get(img_basename)
    if not (img_path and os.path.exists(img_path)):
        img_path = os.path.join("uploads", str(img_basename))
    if img_path and os.path.exists(img_path):
        try:
            with PILImage.open(img_path) as img: iw, ih = img.size
            tw, th = sx(geo["width"]).emu, sy(geo["height"]).emu
            sc = min(tw / iw, th / ih)
            nw, nh = int(iw * sc), int(ih * sc)
            
            ox = sx(geo["left"]).emu + (tw - nw) // 2
            
            # Si es una persona, la pegamos al fondo de su caja (para que no flote)
            if role == "person":
                oy = sy(geo["top"]).emu + (th - nh)
            else:
                oy = sy(geo["top"]).emu + (th - nh) // 2
                
            slide.shapes.add_picture(img_path, ox, oy, nw, nh)
        except: pass
