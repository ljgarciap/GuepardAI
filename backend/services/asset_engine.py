import urllib.request
import urllib.parse
import random
import time
import os
import concurrent.futures

# Pool of diversities
DIVERSITY_SEEDS = ["futuristic", "strategic", "minimalist", "dynamic", "organic", "modern", "visionary", "digital", "vibrant"]

def fetch_single_asset(idx, narrative, entropy_seed):
    # --- CORPORATE QUALITY GUARD (v34.0) ---
    # Pre-pend executive tags to force professional context.
    # --- ELITE CORPORATE FILTER (v38.0) ---
    forbidden = ["puzzle", "gear", "handshake", "metaphor", "concept", "abstract"]
    clean_narrative = narrative.lower()
    for f in forbidden:
        clean_narrative = clean_narrative.replace(f, "corporate")
    
    query = f"executive,professional,clean,office,{clean_narrative}"
    elite_query = f"high-resolution,professional,{query.replace(' ', ',')}"
    url = f"https://loremflickr.com/1920/1080/{elite_query}/all"
    
    filename = f"asset_{idx}_{os.urandom(2).hex()}.jpg"
    path = os.path.join("uploads", filename)
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as res:
                content = res.read()
                # --- BINARY GUARD (v33.0) ---
                # Check for JPEG Magic Bytes (FF D8 FF)
                if len(content) > 5000 and content.startswith(b'\xff\xd8\xff'):
                    with open(path, 'wb') as f:
                        f.write(content)
                    return idx, path
        except:
            # Fallback to broader corporate search (v34.1)
            url = f"https://loremflickr.com/1600/900/modern,executive,office"
            time.sleep(1)
            
    return idx, None

def orchestrate_assets(content_manifest, brand=None, db=None):
    """
    Orquestador de Activos v90.0: Búsqueda Vectorial Semántica + Diversidad Garantizada.
    """
    print(f"[AssetEngine] Orchestrating assets with Vectorized Treasury Protocol v90.0...")
    
    asset_map = {}
    used_asset_ids = set() # Registro para evitar repeticiones
    from services.asset_library_service import find_best_assets
    
    extracted = getattr(brand, "extracted_assets", {}) if brand else {}
    if isinstance(extracted, list):
        extracted = {"photos": extracted, "logos": [], "icons": []}
    elif not isinstance(extracted, dict):
        extracted = {"photos": [], "logos": [], "icons": []}
        
    logos = extracted.get("logos", [])
    num_logos = len(logos)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = []
        for i, slide in enumerate(content_manifest["slides"]):
            slide_idx = slide["slide_number"]
            narrative = slide.get("image_narrative") or "corporate strategy executive professional"
            
            # --- STRATEGY: SEMANTIC VECTOR SEARCH (v12.0) ---
            # Even if 'selected_asset' exists, we now prioritize the VECTOR search
            # to ensure diversity and exclusion logic.
            if db and brand:
                keywords = narrative.lower().replace(",", " ").split()
                
                matches = find_best_assets(
                    db, 
                    brand.id, 
                    keywords, 
                    category="photos", 
                    limit=5,
                    exclude_ids=list(used_asset_ids)
                )
                
                if matches:
                    chosen = matches[0]
                    used_asset_ids.add(chosen.id)
                    asset_map[slide_idx] = chosen.local_path
                    print(f"  [AssetEngine] Vector Search success for Slide {slide_idx}: {chosen.description[:40]}...")
                    continue
                else:
                    # Fallback to pre-selected if vector search yields zero results (unlikely)
                    if slide.get("selected_asset"):
                        path = slide.get("selected_asset")
                        asset_map[slide_idx] = os.path.join("uploads", path) if not path.startswith("uploads/") else path
                        continue
            
            # --- STRATEGY 3: RANDOM LOCAL FALLBACK (Anti-Gato Protocol) ---
            # If all else fails, pick any random photo from the local library
            # instead of going to the internet.
            print(f"  [AssetEngine] CRITICAL: No semantic match for Slide {slide_idx}. Picking random local asset.")
            all_local = db.query(models.BrandAsset).filter(models.BrandAsset.category == "photos").all()
            if all_local:
                chosen = random.choice(all_local)
                asset_map[slide_idx] = chosen.local_path
                continue
            
            # --- STRATEGY 4: LOGO FALLBACK ---
            if num_logos > 0:
                asset_map[slide_idx] = logos[0]
                continue
            
    if num_logos > 0:
        asset_map["global_logo"] = logos[0]

    return asset_map
