"""
visual_dna_service.py — PowerAI
Extracción de DNA Visual: colores, fuentes, assets físicos.
Herramienta: Programático (fitz / python-pptx) + LLM texto ligero.
"""
import os
import json
import uuid
from collections import Counter
from typing import Optional, Callable

from llm_provider import generate_vision_json, generate_json
from dotenv import load_dotenv

load_dotenv()

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from pptx import Presentation
except ImportError:
    Presentation = None


# ──────────────────────────────────────────────
# UTILIDADES
# ──────────────────────────────────────────────

def _hex(r, g, b) -> str:
    return f"#{int(r):02X}{int(g):02X}{int(b):02X}"


def _is_neutral(hex_color: str) -> bool:
    """Descarta blancos, negros y grises muy puros."""
    h = hex_color.upper().lstrip("#")
    if len(h) != 6:
        return True
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    brightness = (r + g + b) / 3
    spread = max(r, g, b) - min(r, g, b)
    return brightness > 230 or brightness < 20 or spread < 15


# ──────────────────────────────────────────────
# EXTRACCIÓN PROGRAMÁTICA — PDF
# ──────────────────────────────────────────────

def extract_pdf_dna(file_path: str, source_filename: str,
                    upload_dir: str, cb: Optional[Callable] = None) -> dict:
    if not fitz:
        return {"error": "PyMuPDF no disponible."}

    doc = fitz.open(file_path)
    fonts, colors, assets = [], [], []
    total = len(doc)

    for i, page in enumerate(doc):
        if cb:
            cb(f"DNA Visual — PDF página {i+1}/{total}", int((i + 1) / total * 90))

        # Texto → fuentes y colores
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("font"):
                        fonts.append(span["font"])
                    c = span.get("color", 0)
                    r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
                    hex_c = _hex(r, g, b)
                    if not _is_neutral(hex_c):
                        colors.append(hex_c)

        # Imágenes nativas
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                base_img = doc.extract_image(xref)
                data = base_img.get("image", b"")
                ext = base_img.get("ext", "png")
                if len(data) > 10240:  # > 10KB
                    uid = uuid.uuid4().hex[:6]
                    fname = f"{source_filename}_p{i}_{uid}.{ext}"
                    out = os.path.join(upload_dir, fname)
                    with open(out, "wb") as f:
                        f.write(data)
                    assets.append(fname)
            except Exception as e:
                print(f"  [DNA] Error extrayendo imagen PDF xref {xref}: {e}", flush=True)

    font_freq = Counter(fonts)
    color_freq = Counter(c for c in colors)

    # --- ASSET EXTRACTION (v80.0 - Library Ready) ---
    labeled_assets = {"photos": [], "logos": [], "icons": []}
    for asset_name in assets:
        category = "photos"
        if "logo" in asset_name.lower(): category = "logos"
        elif "icon" in asset_name.lower(): category = "icons"
        labeled_assets[category].append({"path": asset_name, "description": "extracted raw asset"})

    return {
        "primary_fonts": [f[0] for f in font_freq.most_common(5)],
        "dominant_colors": [c[0] for c in color_freq.most_common(8)],
        "extracted_assets": labeled_assets,
        "source_type": "pdf",
    }


# ──────────────────────────────────────────────
# EXTRACCIÓN PROGRAMÁTICA — PPTX
# ──────────────────────────────────────────────

def extract_pptx_dna(file_path: str, source_filename: str,
                     upload_dir: str, cb: Optional[Callable] = None) -> dict:
    if not Presentation:
        return {"error": "python-pptx no disponible."}

    prs = Presentation(file_path)
    fonts, colors, assets = [], [], []
    total = len(prs.slides)

    for i, slide in enumerate(prs.slides):
        if cb:
            cb(f"DNA Visual — PPTX slide {i+1}/{total}", int((i + 1) / total * 90))

        for shape in slide.shapes:
            # Imágenes
            if getattr(shape, "shape_type", None) == 13:
                try:
                    img_data = shape.image.blob
                    ext = shape.image.ext
                    if len(img_data) > 15360:  # > 15KB
                        uid = uuid.uuid4().hex[:6]
                        fname = f"{source_filename}_s{i}_{uid}.{ext}"
                        out = os.path.join(upload_dir, fname)
                        with open(out, "wb") as f:
                            f.write(img_data)
                        assets.append(fname)
                except Exception as e:
                    print(f"  [DNA] Error extrayendo imagen PPTX slide {i}: {e}", flush=True)

            # Texto → fuentes y colores
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    if run.font.name:
                        fonts.append(run.font.name)
                    try:
                        col = run.font.color
                        if col and hasattr(col, "rgb") and col.rgb:
                            r, g, b = col.rgb
                            hex_c = _hex(r, g, b)
                            if not _is_neutral(hex_c):
                                colors.append(hex_c)
                    except AttributeError:
                        pass

        # Colores de fondo del slide
        try:
            bg = slide.background.fill
            if bg.type is not None and hasattr(bg, "fore_color"):
                fc = bg.fore_color
                if fc and hasattr(fc, "rgb") and fc.rgb:
                    r, g, b = fc.rgb
                    colors.append(_hex(r, g, b))
        except Exception:
            pass

    font_freq = Counter(fonts)
    color_freq = Counter(c for c in colors)

    # --- ASSET EXTRACTION (v80.0 - Library Ready) ---
    labeled_assets = {"photos": [], "logos": [], "icons": []}
    
    for asset_name in assets:
        category = "photos"
        if "logo" in asset_name.lower(): category = "logos"
        elif "icon" in asset_name.lower(): category = "icons"
        
        # Ya no etiquetamos aquí, la Biblioteca lo hará en main.py con Hashing
        labeled_assets[category].append({"path": asset_name, "description": "extracted raw asset"})

    return {
        "primary_fonts": [f[0] for f in font_freq.most_common(5)],
        "dominant_colors": [c[0] for c in color_freq.most_common(8)],
        "extracted_assets": labeled_assets,
        "source_type": "pptx",
    }


# ──────────────────────────────────────────────
# REFINAMIENTO CON LLM TEXTO
# ──────────────────────────────────────────────

def refine_dna_with_llm(raw_data: dict, cb: Optional[Callable] = None) -> dict:
    if cb:
        cb("DNA Visual — Sintetizando con LLM...", 92)

    prompt = f"""
You are a Senior Brand Identity Expert. 
Based on programmatically extracted data from an official document:

{json.dumps(raw_data, indent=2)}

Your mission: Synthesize the brand's Visual DNA with high accuracy.

STRICT COLOR RULES:
1. primary_color: This MUST be the main institutional color (e.g., Tesco Blue #00539F). Ignore noise colors from photos or charts.
2. secondary_color: A distinct secondary brand color (e.g., Tesco Red #EE1C2E). Must have high contrast with primary.
3. background_color: Usually #FFFFFF or a very light brand tint.
4. text_main_color: Usually #000000 or very dark grey/navy for readability.
5. accent_color: A vibrant accent color if present, or null.

Return ONLY this JSON:
{{
  "primary_color": "#XXXXXX",
  "secondary_color": "#XXXXXX",
  "background_color": "#XXXXXX",
  "text_main_color": "#XXXXXX",
  "accent_color": "#XXXXXX or null",
  "primary_font": "font name",
  "secondary_font": "font name or null"
}}
"""
    try:
        result = generate_json(prompt, specialization="general")
        result["extracted_assets"] = raw_data.get("extracted_assets", [])
        result["raw_extraction"] = raw_data
        return result
    except Exception as e:
        print(f"  [DNA] LLM refinement failed: {e}", flush=True)
        # Fallback determinístico
        fonts = raw_data.get("primary_fonts", ["Arial"])
        colors = raw_data.get("dominant_colors", ["#333333"])
        return {
            "primary_color": colors[0] if len(colors) > 0 else "#333333",
            "secondary_color": colors[1] if len(colors) > 1 else "#666666",
            "background_color": "#FFFFFF",
            "text_main_color": "#111111",
            "accent_color": colors[2] if len(colors) > 2 else None,
            "primary_font": fonts[0] if fonts else "Arial",
            "secondary_font": fonts[1] if len(fonts) > 1 else None,
            "extracted_assets": raw_data.get("extracted_assets", []),
            "raw_extraction": raw_data,
            "llm_error": str(e),
        }


# ──────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ──────────────────────────────────────────────

def extract_visual_dna(file_path: str, upload_dir: str,
                       cb: Optional[Callable] = None) -> dict:
    """
    Punto de entrada principal.
    Retorna el diccionario de DNA visual listo para persistir en brand_visual_dna.
    """
    source_filename = os.path.basename(file_path)
    ext = os.path.splitext(file_path)[1].lower()

    if cb:
        cb("DNA Visual — Iniciando extracción...", 2)

    if ext == ".pdf":
        raw = extract_pdf_dna(file_path, source_filename, upload_dir, cb)
    elif ext == ".pptx":
        raw = extract_pptx_dna(file_path, source_filename, upload_dir, cb)
    else:
        return {"error": f"Formato no soportado: {ext}"}

    if "error" in raw:
        return raw

    return refine_dna_with_llm(raw, cb)
