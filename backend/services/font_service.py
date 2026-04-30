import os
import requests
import logging
import subprocess

logger = logging.getLogger(__name__)

# Directorio de fuentes en el contenedor (estándar Linux)
FONT_DIR = os.path.expanduser("~/.local/share/fonts")
if not os.path.exists(FONT_DIR):
    os.makedirs(FONT_DIR, exist_ok=True)

# Mapa de fuentes comunes que sabemos que están en Google Fonts
GOOGLE_FONTS_MAP = {
    "inter": "Inter",
    "outfit": "Outfit",
    "montserrat": "Montserrat",
    "roboto": "Roboto",
    "open sans": "Open+Sans",
    "lato": "Lato",
    "poppins": "Poppins",
    "playfair display": "Playfair+Display",
    "oswald": "Oswald",
    "raleway": "Raleway",
    "source sans pro": "Source+Sans+Pro",
    "ubuntu": "Ubuntu",
    "merriweather": "Merriweather",
    "pt sans": "PT+Sans",
    "nunito": "Nunito",
    "noto sans": "Noto+Sans"
}

def install_font(font_name: str) -> Optional[str]:
    """
    Searches for and installs a font from Google Fonts.
    Returns the actual font family name installed or None.
    """
    font_name_lower = font_name.lower().strip()
    
    # 1. Check if already installed
    safe_name = font_name.replace(" ", "_")
    target_path = os.path.join(FONT_DIR, f"{safe_name}.ttf")
    
    if os.path.exists(target_path):
        return font_name

    # 2. Search in Google Fonts map
    gf_name = GOOGLE_FONTS_MAP.get(font_name_lower)
    actual_family = font_name
    if not gf_name:
        gf_name = font_name.replace(" ", "+")
    else:
        actual_family = GOOGLE_FONTS_MAP[font_name_lower].replace("+", " ")

    print(f"  [FontService] Attempting to sync font: {font_name}...", flush=True)
    
    download_url = f"https://fonts.google.com/download?family={gf_name}"
    
    try:
        response = requests.get(download_url, timeout=10)
        if response.status_code == 200:
            import zipfile
            import io
            
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                for file_info in z.infolist():
                    if file_info.filename.endswith(".ttf"):
                        filename = os.path.basename(file_info.filename)
                        dest = os.path.join(FONT_DIR, filename)
                        with open(dest, "wb") as f:
                            f.write(z.read(file_info))
            
            # 3. Update system font cache
            subprocess.run(["fc-cache", "-f", FONT_DIR], check=True)
            print(f"  [FontService] Font '{actual_family}' INSTALLED and cached.", flush=True)
            return actual_family
    except Exception as e:
        print(f"  [FontService] Failed to install {font_name}: {e}", flush=True)
    
    return None

def ensure_brand_fonts(db, brand_id: int, visual_dna: dict):
    """
    Ensures visual DNA fonts are available and updates DB with real family names.
    """
    updated = False
    
    # Process Primary Font
    p_font = visual_dna.get("primary_font")
    if p_font:
        actual = install_font(p_font)
        if actual and actual != p_font:
            visual_dna["primary_font"] = actual
            updated = True

    # Process Secondary Font
    s_font = visual_dna.get("secondary_font")
    if s_font:
        actual = install_font(s_font)
        if actual and actual != s_font:
            visual_dna["secondary_font"] = actual
            updated = True
            
    if updated:
        import models
        record = db.query(models.BrandVisualDna).filter(models.BrandVisualDna.brand_id == brand_id).first()
        if record:
            record.primary_font = visual_dna.get("primary_font")
            record.secondary_font = visual_dna.get("secondary_font")
            db.commit()
            print(f"  [FontService] Database updated with synchronized font names.", flush=True)
