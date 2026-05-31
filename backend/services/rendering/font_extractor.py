import os
import uuid
import zipfile
import subprocess
import xml.etree.ElementTree as ET
import logging

logger = logging.getLogger(__name__)

# Directorio de fuentes en el contenedor (estándar Linux o el nuestro)
FONT_DIR = "/usr/share/fonts/custom"
if not os.path.exists(FONT_DIR):
    try:
        os.makedirs(FONT_DIR, exist_ok=True)
    except Exception:
        FONT_DIR = os.path.expanduser("~/.local/share/fonts")
        os.makedirs(FONT_DIR, exist_ok=True)

def deobfuscate_font(data: bytes, guid_str: str) -> bytearray:
    """
    Desofusca un archivo .fntdata (ODTTF) utilizando el GUID original.
    Aplica XOR inverso usando Little Endian.
    """
    try:
        # Remover llaves si existen e instanciar UUID
        guid_clean = guid_str.replace("{", "").replace("}", "")
        guid_obj = uuid.UUID(guid_clean)
        guid_bytes = guid_obj.bytes_le
        
        deobfuscated_data = bytearray(data)
        for i in range(min(32, len(data))):
            gi = 16 - (i % 16) - 1
            deobfuscated_data[i] ^= guid_bytes[gi]
            
        return deobfuscated_data
    except Exception as e:
        logger.warning(f"Error desofuscando fuente {guid_str}: {e}")
        return bytearray(data)

def extract_and_install_fonts(pptx_path: str):
    if not os.path.exists(pptx_path): return
    extracted_any = False
    
    try:
        with zipfile.ZipFile(pptx_path, 'r') as zip_ref:
            namespaces = {
                'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
                'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
            }
            
            # --- TIPO 1: ODTTF ofuscado en ppt/fontTable.xml ---
            font_mapping_odttf = {} # rId -> (fontKey, typeface)
            if 'ppt/fontTable.xml' in zip_ref.namelist():
                xml_data = zip_ref.read('ppt/fontTable.xml')
                root = ET.fromstring(xml_data)
                for font_node in root.findall('.//p:font', namespaces):
                    typeface = font_node.get('name', 'Unknown')
                    embed_node = font_node.find('./p:embedRegular', namespaces)
                    if embed_node is not None:
                        font_key = embed_node.get('fontKey')
                        r_id = embed_node.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                        if font_key and r_id: font_mapping_odttf[r_id] = (font_key, typeface)
            
            rel_mapping_fonts = {}
            if 'ppt/_rels/fontTable.xml.rels' in zip_ref.namelist():
                rels_root = ET.fromstring(zip_ref.read('ppt/_rels/fontTable.xml.rels'))
                for rel in rels_root.findall('.//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'):
                    rel_mapping_fonts[rel.get('Id')] = f"ppt/{rel.get('Target')}"
                    
            for r_id, (guid, typeface) in font_mapping_odttf.items():
                fntdata_path = rel_mapping_fonts.get(r_id)
                if fntdata_path and fntdata_path in zip_ref.namelist():
                    clean_data = deobfuscate_font(zip_ref.read(fntdata_path), guid)
                    safe_name = "".join(c for c in typeface if c.isalnum() or c in " -_").strip()
                    dest_path = os.path.join(FONT_DIR, f"{safe_name}.ttf")
                    with open(dest_path, "wb") as f: f.write(clean_data)
                    logger.info(f"[FontExtractor] ODTTF '{typeface}' desofuscada -> {dest_path}")
                    extracted_any = True

            # --- TIPO 2: EOT en ppt/presentation.xml ---
            font_mapping_eot = {} # rId -> typeface
            if 'ppt/presentation.xml' in zip_ref.namelist():
                xml_data = zip_ref.read('ppt/presentation.xml')
                root = ET.fromstring(xml_data)
                for embed_node in root.findall('.//p:embeddedFont', namespaces):
                    font_node = embed_node.find('./p:font', namespaces)
                    reg_node = embed_node.find('./p:regular', namespaces)
                    if font_node is not None and reg_node is not None:
                        typeface = font_node.get('typeface', 'Unknown')
                        r_id = reg_node.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                        if r_id: font_mapping_eot[r_id] = typeface
            
            rel_mapping_pres = {}
            if 'ppt/_rels/presentation.xml.rels' in zip_ref.namelist():
                rels_root = ET.fromstring(zip_ref.read('ppt/_rels/presentation.xml.rels'))
                for rel in rels_root.findall('.//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'):
                    rel_mapping_pres[rel.get('Id')] = f"ppt/{rel.get('Target')}"
                    
            for r_id, typeface in font_mapping_eot.items():
                fntdata_path = rel_mapping_pres.get(r_id)
                if fntdata_path and fntdata_path in zip_ref.namelist():
                    raw_data = zip_ref.read(fntdata_path)
                    safe_name = "".join(c for c in typeface if c.isalnum() or c in " -_").strip()
                    eot_path = os.path.join(FONT_DIR, f"{safe_name}.eot")
                    ttf_path = os.path.join(FONT_DIR, f"{safe_name}.ttf")
                    
                    with open(eot_path, "wb") as f: f.write(raw_data)
                    
                    # Convert EOT to TTF using fontforge
                    try:
                        subprocess.run([
                            "fontforge", "-lang=ff", "-c", 
                            "Open($1); Generate($2)", eot_path, ttf_path
                        ], check=True, capture_output=True)
                        logger.info(f"[FontExtractor] EOT '{typeface}' converted to TTF -> {ttf_path}")
                        extracted_any = True
                    except Exception as e:
                        logger.error(f"[FontExtractor] Failed to convert EOT {typeface}: {e}")
                        logger.info(f"[FontExtractor] Attempting to download '{typeface}' from Google Fonts fallback...")
                        try:
                            import urllib.request
                            import zipfile
                            import io
                            url = f"https://fonts.google.com/download?family={typeface.replace(' ', '%20')}"
                            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                            resp = urllib.request.urlopen(req, timeout=10)
                            with zipfile.ZipFile(io.BytesIO(resp.read())) as z:
                                for name in z.namelist():
                                    if name.lower().endswith(".ttf"):
                                        with open(ttf_path, "wb") as f_out:
                                            f_out.write(z.read(name))
                                        logger.info(f"[FontExtractor] Success! {typeface} downloaded from Google Fonts.")
                                        extracted_any = True
                                        break
                        except Exception as dl_e:
                            logger.error(f"[FontExtractor] Could not download {typeface} from Google Fonts: {dl_e}")
                    finally:
                        if os.path.exists(eot_path): os.remove(eot_path)

        if extracted_any:
            print("[FontExtractor] Updating Linux font cache...", flush=True)
            subprocess.run(["fc-cache", "-f", FONT_DIR], check=False)
            
    except Exception as e:
        logger.error(f"Error procesando tipografías del PPTX: {e}")
