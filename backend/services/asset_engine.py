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
    print(f"[AssetEngine] Orchestrating assets with Brand Fidelity Protocol v80.0 (Library Aware)...")
    
    asset_map = {}
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
            narrative = slide.get("image_narrative") or "corporate"
            
            # --- STRATEGY: CURATED ASSET (v50.0) ---
            if slide.get("selected_asset"):
                path = slide.get("selected_asset")
                if path and not path.startswith("uploads/"):
                    path = os.path.join("uploads", path)
                asset_map[slide_idx] = path
                continue

            # 1. Intentar buscar en la Biblioteca Semántica de la Marca
            if db and brand:
                keywords = narrative.lower().replace(",", " ").split()
                matches = find_best_assets(db, brand.id, keywords, category="photos", limit=5)
                
                if matches:
                    # Evitar usar la misma imagen si hay opciones
                    chosen = matches[i % len(matches)]
                    asset_map[slide_idx] = chosen.local_path
                    print(f"  [AssetEngine] Library Match for Slide {slide_idx}: {chosen.description} (tags: {chosen.tags})")
                    continue
            
            # --- FALLBACK: LOGO AS WATERMARK (if no photos found) ---
            if num_logos > 0:
                # Better to have a logo than a random cat statue
                asset_map[slide_idx] = logos[0]
                continue

            # --- LAST RESORT: EXTERNAL STOCK (Professional Only) ---
            narrative = slide.get("image_narrative", "corporate strategy")
            seed = DIVERSITY_SEEDS[i % len(DIVERSITY_SEEDS)]
            futures.append(ex.submit(fetch_single_asset, slide_idx, narrative, seed))
            
        for f in concurrent.futures.as_completed(futures):
            idx, path = f.result()
            if path:
                asset_map[idx] = path
            
    # Also add the main logo to the asset map for global access
    if num_logos > 0:
        asset_map["global_logo"] = logos[0]

    return asset_map
