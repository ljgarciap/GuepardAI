"""
artistic_essence_service.py — PowerAI
Extracción de Esencia Artística: layouts, gestos de diseñador, composición.
Herramienta: Vision LLM (Claude Sonnet con visión) — VE las slides, no las lee.
"""
import os
import json
import base64
from typing import Optional, Callable, List

from llm_provider import generate_vision_json
from dotenv import load_dotenv

load_dotenv()

try:
    import fitz  # PyMuPDF — renderizar PDF como imágenes
except ImportError:
    fitz = None

try:
    from pptx import Presentation
    from pptx.util import Inches
except ImportError:
    Presentation = None


# ──────────────────────────────────────────────
# CONVERSIÓN A IMÁGENES
# ──────────────────────────────────────────────

MAX_SLIDES_TO_ANALYZE = 10  # Analiza máximo N slides para controlar costo/tiempo


def _pdf_to_images(file_path: str, out_dir: str, max_pages: int = MAX_SLIDES_TO_ANALYZE) -> List[str]:
    """Convierte las primeras N páginas de un PDF a PNG."""
    if not fitz:
        raise ImportError("PyMuPDF no disponible para convertir PDF a imágenes.")

    doc = fitz.open(file_path)
    image_paths = []
    total = min(len(doc), max_pages)

    for i in range(total):
        page = doc[i]
        # mat = Matrix para escala — 2.0 da resolución decente sin ser excesivo
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        fname = os.path.join(out_dir, f"_vision_page_{i}.png")
        pix.save(fname)
        image_paths.append(fname)

    doc.close()
    return image_paths


def _pptx_to_images(file_path: str, out_dir: str, max_slides: int = MAX_SLIDES_TO_ANALYZE) -> List[str]:
    """
    Convierte slides PPTX a PNG usando fitz si está disponible (vía conversión temporal),
    o extrae thumbnails embebidos si existen.
    Estrategia: Renderizar cada slide como imagen PNG con la librería python-pptx + Pillow.
    """
    image_paths = []

    # Estrategia 1: Usar fitz si el archivo se puede convertir a PDF temporal (más fiel)
    # En macOS/Linux, LibreOffice headless puede hacer esto, pero no siempre está disponible.
    # Estrategia 2: Extraer slide thumbnails embebidos en el PPTX (si existen)
    if Presentation:
        prs = Presentation(file_path)
        total = min(len(prs.slides), max_slides)

        for i in range(total):
            slide = prs.slides[i]

            # Intentar extraer thumbnail embebido (PowerPoint a veces los incluye)
            try:
                slide_part = slide.part
                thumb_rel = None
                for rel in slide_part.rels.values():
                    if "thumbnail" in rel.reltype.lower():
                        thumb_rel = rel
                        break

                if thumb_rel:
                    thumb_data = thumb_rel.target_part.blob
                    fname = os.path.join(out_dir, f"_vision_slide_{i}.jpg")
                    with open(fname, "wb") as f:
                        f.write(thumb_data)
                    image_paths.append(fname)
                    continue
            except Exception:
                pass

            # Fallback: Capturar imágenes de la slide con Pillow (Versión Reforzada v2)
            try:
                from PIL import Image, ImageDraw
                W, H = 1280, 720
                img = Image.new("RGB", (W, H), color=(255, 255, 255))
                draw = ImageDraw.Draw(img)

                # 1. Fondo de la slide
                try:
                    bg = slide.background.fill
                    if hasattr(bg, "fore_color") and bg.fore_color and hasattr(bg.fore_color, "rgb"):
                        rgb = bg.fore_color.rgb
                        img = Image.new("RGB", (W, H), color=(rgb[0], rgb[1], rgb[2]))
                        draw = ImageDraw.Draw(img)
                except: pass

                # 2. Dibujar TODOS los shapes (no solo fotos)
                slide_w, slide_h = prs.slide_width, prs.slide_height
                for shape in slide.shapes:
                    try:
                        # Coordenadas proporcionales
                        x = int(shape.left / slide_w * W)
                        y = int(shape.top / slide_h * H)
                        w = int(shape.width / slide_w * W)
                        h = int(shape.height / slide_h * H)

                        # Si es una imagen (Shape 13)
                        if getattr(shape, "shape_type", None) == 13:
                            from io import BytesIO
                            shape_img = Image.open(BytesIO(shape.image.blob)).convert("RGBA")
                            shape_img = shape_img.resize((max(w, 1), max(h, 1)))
                            img.paste(shape_img, (x, y), shape_img if shape_img.mode == "RGBA" else None)
                        
                        # Si tiene texto (cualquier forma con texto)
                        elif shape.has_text_frame:
                            # Dibujamos un bloque que represente la masa visual del texto
                            draw.rectangle([x, y, x + w, y + h], outline=(180, 180, 180), width=2)
                            txt = shape.text_frame.text[:50].replace("\n", " ")
                            draw.text((x + 5, y + 5), txt, fill=(80, 80, 80))
                        
                        # Si es una forma geométrica (AutoShape)
                        else:
                            # Al menos dibujamos el bounding box para que la IA vea la estructura
                            draw.rectangle([x, y, x + w, y + h], outline=(220, 220, 220))
                    except: continue

                fname = os.path.join(out_dir, f"_vision_slide_{i}.png")
                img.save(fname)
                image_paths.append(fname)
                print(f"  [Essence] Slide {i} rendered successfully.", flush=True)

            except Exception as e:
                print(f"  [Essence] Pillow fallback failed on slide {i}: {e}", flush=True)

            except ImportError:
                # Si no hay Pillow, crear imagen placeholder mínima
                print(f"  [Essence] Pillow no disponible. Slide {i} sin imagen.", flush=True)

    return image_paths


# ──────────────────────────────────────────────
# PROMPT: ANÁLISIS DE SLIDE INDIVIDUAL (v3.0)
# ──────────────────────────────────────────────

ART_DIRECTOR_PROMPT = """
Analyze this SINGLE slide from a brand manual. 
Identify the micro-design gestures and structural rules present in THIS image.

EXTRACT:
1. MARGINS & ZONES: Precise coordinates (%) for title and content.
2. GRAPHIC OBJECTS: Identify specific shapes (pill-banners, boxes, rounded containers, lines).
3. BRAND PUNCTUATION: Tiny details (dots at end of titles, specific bullet symbols, page number style).
4. COMPOSITION: Is it a 2-column grid? Is there a split between media and text?

Output ONLY this JSON:
{
  "structural": {"title_y": 10, "content_y": 40, "margin_left": 10, "grid": "2-column | 1-column"},
  "gestures": {"pill_banners": true/false, "red_dot": true/false, "rounded_corners": true/false, "accents": "description"},
  "density": "high | medium | low",
  "note": "Short technical description of this specific slide"
}
"""

# ──────────────────────────────────────────────
# PROMPT: SINTETIZADOR DE IDENTIDAD (v1.0)
# ──────────────────────────────────────────────

SYNTHESIZER_PROMPT = """
You are a Brand Guardian. Below are several individual analyses of slides from the same brand.
Your task is to CONSOLIDATE these findings into a single, cohesive Architectural DNA.

RULES:
1. RECURRENCE: If a gesture (like pill-banners or a red dot) appears in multiple slides, it is a CORE RULE.
2. PROPORTIONS: Average the coordinates but favor the most common pattern.
3. TONE: Determine if the brand is 'Airy' or 'Modular/Dense'.

Output ONLY the final Brand Identity JSON:
{
  "structural_archetypes": {
    "title_top": 10,
    "title_height": 20,
    "content_start_y": 40,
    "margin_left": 10,
    "column_grid": "2-column | 1-column",
    "bullet_symbol": "dot | dash | arrow"
  },
  "design_gestures": {
    "corner_style": "sharp | rounded | pill",
    "accent_geometry": "vertical-line-left | horizontal-bar-top | title-underline | red-dot | pill-banners | none",
    "uses_overlays": true,
    "overlay_opacity": 0.4
  },
  "composition_rules": {
    "text_safe_zone": "top-left | center-left | bottom-third",
    "visual_density": "high | medium | low",
    "padding_level": "airy | compact"
  },
  "art_direction_note": "A final master summary of how to replicate this specific look"
}
"""


# ──────────────────────────────────────────────
# ANÁLISIS ITERATIVO + CONSOLIDACIÓN
# ──────────────────────────────────────────────

def analyze_with_vision(image_paths: List[str], cb: Optional[Callable] = None) -> dict:
    """Procesa cada slide individualmente y luego consolida la esencia global."""
    if not image_paths:
        return {"error": "No images to analyze."}

    # Path dinámico para el log de auditoría
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    audit_dir = os.path.join(base_dir, "data")
    os.makedirs(audit_dir, exist_ok=True)
    audit_file = os.path.join(audit_dir, "vision_audit.log")

    import datetime
    import json
    from llm_provider import generate_json
    
    micro_essences = []
    total = len(image_paths)

    for idx, path in enumerate(image_paths):
        step_pct = 60 + int((idx / total) * 30)
        if cb:
            cb(f"Esencia Artística — Analizando slide {idx+1}/{total}...", step_pct)
        
        try:
            # Análisis individual
            res = generate_vision_json(ART_DIRECTOR_PROMPT, [path])
            micro_essences.append(res)
            
            # Log individual
            with open(audit_file, "a") as f:
                f.write(f"\n[{datetime.datetime.now()}] SLIDE {idx} Analysis: {json.dumps(res)}\n")
        except Exception as e:
            print(f"  [Essence] Slide {idx} failed: {e}")

    # --- SÍNTESIS FINAL ---
    if cb:
        cb("Esencia Artística — Consolidando identidad de marca...", 95)
    
    try:
        final_prompt = f"{SYNTHESIZER_PROMPT}\n\nINDIVIDUAL ANALYSES:\n{json.dumps(micro_essences, indent=2)}"
        final_identity = generate_json(final_prompt, specialization="general")
        
        with open(audit_file, "a") as f:
            f.write(f"\n[{datetime.datetime.now()}] FINAL CONSOLIDATED IDENTITY:\n{json.dumps(final_identity, indent=2)}\n")
            f.write("============================================================\n")
            
        return final_identity
    except Exception as e:
        print(f"  [Essence] Synthesis failed: {e}")
        return {"error": str(e)}


# ──────────────────────────────────────────────
# LIMPIEZA DE IMÁGENES TEMPORALES
# ──────────────────────────────────────────────

def _cleanup_images(image_paths: List[str]):
    for p in image_paths:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


# ──────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ──────────────────────────────────────────────

def extract_artistic_essence(file_path: str, upload_dir: str,
                              cb: Optional[Callable] = None) -> dict:
    """
    Punto de entrada principal.
    Retorna el diccionario de Esencia Artística listo para persistir en brand_artistic_essence.
    """
    # Detección flexible de extensión
    fn_lower = file_path.lower()
    
    if cb:
        cb("Esencia Artística — Analizando tipo de archivo...", 5)

    image_paths = []
    try:
        if fn_lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
            # Si ya es una imagen, la usamos directamente
            image_paths = [file_path]
        elif ".pdf" in fn_lower:
            image_paths = _pdf_to_images(file_path, upload_dir)
        elif ".pptx" in fn_lower:
            image_paths = _pptx_to_images(file_path, upload_dir)
        else:
            return {"error": f"Formato no soportado o irreconocible: {os.path.basename(file_path)}"}
    except Exception as e:
        return {"error": f"Error procesando archivo: {e}"}

    if not image_paths:
        return {"error": "No se pudieron generar imágenes del documento."}

    if cb:
        cb(f"Esencia Artística — {len(image_paths)} imágenes generadas. Enviando a Vision LLM...", 40)

    # 2. Analizar con Vision LLM
    vision_result = analyze_with_vision(image_paths, cb)

    # 3. Limpiar imágenes temporales
    _cleanup_images(image_paths)

    if cb:
        cb("Esencia Artística — Análisis completado.", 98)

    # 4. Normalizar y retornar
    return {
        "structural_archetypes": vision_result.get("structural_archetypes", {}),
        "design_gestures":      vision_result.get("design_gestures", {}),
        "composition_rules":    vision_result.get("composition_rules", {}),
        "art_direction_note":   vision_result.get("art_direction_note", ""),
        "raw_vision_response":  vision_result,
    }
