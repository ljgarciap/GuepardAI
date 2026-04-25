import os
import sys
import json
from collections import Counter
from llm_provider import generate_json
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

def get_hex_from_rgb(r, g, b):
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}".upper()

def extract_pdf_style(file_path, client_name="brand", update_callback=None):
    if not fitz:
        return {"error": "PyMuPDF not found."}
        
    doc = fitz.open(file_path)
    fonts = []
    colors = []
    extracted_assets = []
    
    total_pages = len(doc)
    print(f"  [DNA] Extracting metadata from PDF: {os.path.basename(file_path)} ({total_pages} pages)")
    
    for i, page in enumerate(doc):
        # Callback with progressive percentage (0-100 relative to this phase)
        if update_callback:
            perc = int(((i + 1) / total_pages) * 100)
            update_callback(f"Extracting visual DNA: Page {i+1} of {total_pages}...", perc)
            
        dict_text = page.get_text("dict")
        if "blocks" not in dict_text: continue
            
        for block in dict_text["blocks"]:
            if "lines" not in block: continue
            for line in block["lines"]:
                for span in line.get("spans", []):
                    if "font" in span: fonts.append(span["font"])
                    if "color" in span:
                        c_int = span["color"]
                        r, g, b = (c_int >> 16) & 255, (c_int >> 8) & 255, c_int & 255
                        colors.append(get_hex_from_rgb(r, g, b))
                        colors.append(get_hex_from_rgb(r, g, b))

        # Extract native images from PDF (requires fitz to extract xrefs)
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image.get("image")
                ext = base_image.get("ext", "png")
                
                # Check basic dimensions (rough heuristic, skipping small icons)
                # PyMuPDF usually provides w, h in the get_images tuple but extract_image gives it too in metadata sometimes, 
                # let's just check length size directly (e.g. > 10KB)
                if image_bytes and len(image_bytes) > 10240:
                    import uuid
                    uid_str = uuid.uuid4().hex[:6]
                    img_filename = f"{client_name}_asset_pdf_{i}_{uid_str}.{ext}"
                    out_path = os.path.join(os.path.dirname(file_path), img_filename)
                    with open(out_path, "wb") as f_out:
                        f_out.write(image_bytes)
                    extracted_assets.append(out_path)
            except Exception as e:
                print(f"    [DNA] Failed to extract pdf image xref {xref}: {e}")

    print(f"  [DNA] Raw PDF extraction complete. Found {len(extracted_assets)} valid images.")
    font_counts = Counter(fonts)
    color_counts = Counter(c for c in colors if c not in ["#000000", "#FFFFFF"])
    
    return {
        "primary_fonts": [f[0] for f in font_counts.most_common(5)],
        "dominant_colors": [c[0] for c in color_counts.most_common(5)],
        "extracted_assets": extracted_assets,
        "type": "pdf_extraction"
    }

def extract_pptx_style(file_path, client_name="brand", update_callback=None):
    if not Presentation:
        return {"error": "python-pptx not found."}
        
    prs = Presentation(file_path)
    fonts = []
    colors = []
    extracted_assets = []
    
    total_slides = len(prs.slides)
    print(f"  [DNA] Extracting metadata from PPTX: {os.path.basename(file_path)} ({total_slides} slides)")
    
    for i, slide in enumerate(prs.slides):
        if update_callback:
            perc = int(((i + 1) / total_slides) * 100)
            update_callback(f"Extracting visual DNA: Slide {i+1} of {total_slides}...", perc)

        for shape in slide.shapes:
            # Extract native images from PPTX
            if getattr(shape, "shape_type", None) == 13: # MSO_SHAPE_TYPE.PICTURE
                try:
                    image = shape.image
                    image_bytes = image.blob
                    ext = image.ext
                    # Skip tiny decorative icons (< 100x100 approx) or < 15KB size 
                    if len(image_bytes) > 15360:
                        import uuid
                        uid_str = uuid.uuid4().hex[:6]
                        img_filename = f"{client_name}_asset_{i}_{uid_str}.{ext}"
                        out_path = os.path.join(os.path.dirname(file_path), img_filename)
                        with open(out_path, "wb") as f_out:
                            f_out.write(image_bytes)
                        extracted_assets.append(out_path)
                except Exception as e:
                    print(f"    [DNA] Failed to extract pptx image: {e}")

            if not shape.has_text_frame: continue
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    if run.font.name: fonts.append(run.font.name)
                    try:
                        color = run.font.color
                        if color and hasattr(color, 'rgb') and color.rgb:
                            r, g, b = color.rgb
                            colors.append(get_hex_from_rgb(r, g, b))
                    except AttributeError: pass
                        
    print(f"  [DNA] Raw PPTX extraction complete. Found {len(extracted_assets)} valid images.")
    font_counts = Counter(fonts)
    color_counts = Counter(c for c in colors if c not in ["#000000", "#FFFFFF"])
    
    return {
        "primary_fonts": [f[0] for f in font_counts.most_common(5)],
        "dominant_colors": [c[0] for c in color_counts.most_common(5)],
        "extracted_assets": extracted_assets,
        "type": "pptx_extraction"
    }

def refine_style_with_llm(extracted_data, update_callback=None):
    if update_callback:
        update_callback("Analyzing brand DNA statistics for deterministic synthesis...", 85)
        
    prompt = f"""
    Expert Corporate Art Director & Brand Analyst.
    Data extracted from official documents: {json.dumps(extracted_data)}
    
    Mission: Synthesize a Deterministic Brand DNA based on STATISTICAL FREQUENCY.
    
    STRICT RULES (PRECISION ONLY):
    1. Color Selection: You MUST use the highest-frequency colors from 'dominant_colors' as Primary and Secondary. 
       - Primary: Most frequent color (exclude #000000/#FFFFFF).
       - Secondary: Second most frequent color that provides high contrast.
       - IMPORTANT: If the document mentions other brands (Tesco, partners), DO NOT use their colors (e.g. Mc uses Red/Yellow, ignore any Blue from Tesco).
    
    2. Layout Archetype:
       - 'visual_density': (High/Medium/Low). 
       - 'header_gravity': (Massive/Executive/Light).
       - 'accent_style': (Dot/Line/None). 
    
    3. Visual Identity Strategy (Deterministic Rules):
       Define a set of STRICT geometric and stylistic rules for this brand:
       - 'logo_position': (Top-Right | Top-Left | Bottom-Right).
       - 'accent_geometry': (Vertical-Line | Horizontal-Bar | Floating-Dot).
       - 'typography_pairing': (High-Contrast | Minimalist | Executive).
       - 'layout_preference': (Full-Bleed | Minimal-Clean | Cinematic-Dark).
    
    4. Output Format: JSON ONLY.
    {{
      "primary_color": "#...",
      "secondary_color": "#...",
      "background_color": "#...",
      "text_main_color": "#...",
      "primary_font": "...", 
      "secondary_font": "...",
      "visual_patterns": {{ "density": "...", "gravity": "...", "accent": "..." }},
      "visual_strategy": {{
          "logo_position": "...",
          "accent_geometry": "...",
          "typography_pairing": "...",
          "layout_preference": "...",
          "rules": ["Rule 1", "Rule 2"]
      }},
      "tone_guideline": "..."
    }}
    """
    
    try:
        llm_json = generate_json(prompt, specialization="design")
        if "brand_style" in llm_json: llm_json = llm_json["brand_style"]
        
        # Elevate extracted assets to top level and clean paths (basenames only)
        assets = extracted_data.get("extracted_assets", [])
        llm_json["extracted_assets"] = [os.path.basename(p) for p in assets]
        
        llm_json["raw_extraction"] = extracted_data
        return llm_json
    except Exception as e:
        extracted_data["llm_error"] = str(e)
        return extracted_data

def main(file_path, client_name="brand", update_callback=None):
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        result = extract_pdf_style(file_path, client_name, update_callback)
    elif ext == ".pptx":
        result = extract_pptx_style(file_path, client_name, update_callback)
    else:
        result = {"error": f"Unsupported manual type: {ext}"}
        
    if "error" not in result:
        final_style = refine_style_with_llm(result, update_callback)
    else:
        final_style = result
        
    output_path = os.path.join(os.path.dirname(file_path), "style.json")
    with open(output_path, "w") as f:
        json.dump(final_style, f, indent=2)
        
    return final_style

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python style_extractor.py <file_path>")
        sys.exit(1)
    main(sys.argv[1])
