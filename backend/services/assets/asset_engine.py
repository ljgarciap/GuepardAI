import urllib.request
import urllib.parse
import random
import time
import os
import concurrent.futures
import models

# Pool of diversities
DIVERSITY_SEEDS = ["futuristic", "strategic", "minimalist", "dynamic", "organic", "modern", "visionary", "digital", "vibrant"]

def fetch_single_asset(idx, narrative, entropy_seed):
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
                if len(content) > 5000 and content.startswith(b'\xff\xd8\xff'):
                    with open(path, 'wb') as f:
                        f.write(content)
                    return idx, path
        except:
            url = f"https://loremflickr.com/1600/900/modern,executive,office"
            time.sleep(1)
            
    return idx, None

def orchestrate_assets(content_manifest, brand=None, db=None):
    """
    Orquestador de Activos v90.1: Corrected Semantic Vector Search.
    """
    print(f"[AssetEngine] Orchestrating assets with Vectorized Treasury Protocol v90.1...")
    
    asset_map = {}
    used_asset_ids = set()
    from services.assets.asset_library_service import find_best_assets
    
    extracted = getattr(brand, "extracted_assets", {}) if brand else {}
    if isinstance(extracted, list):
        extracted = {"photos": extracted, "logos": [], "icons": []}
    elif not isinstance(extracted, dict):
        extracted = {"photos": [], "logos": [], "icons": []}
        
    logos = extracted.get("logos", [])
    num_logos = len(logos)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for i, slide in enumerate(content_manifest["slides"]):
            slide_idx = slide["slide_number"]
            narrative = slide.get("image_narrative") or "corporate strategy executive professional"
            
            if db and brand:
                # --- CRITICAL FIX: Use brand_id, not DNA internal ID ---
                target_id = getattr(brand, "brand_id", brand.id)
                print(f"  [AssetEngine] Slide {slide_idx}: Searching for '{narrative}' in Brand ID {target_id}...")
                
                keywords = narrative.lower().replace(",", " ").split()
                matches = find_best_assets(
                    db, 
                    target_id, 
                    keywords, 
                    category="photos", 
                    limit=5,
                    exclude_ids=list(used_asset_ids)
                )
                
                if matches:
                    chosen = matches[0]
                    used_asset_ids.add(chosen.id)
                    asset_map[slide_idx] = chosen.local_path
                    print(f"  [AssetEngine] Success! Found: {chosen.description[:40]} at {chosen.local_path}")
                    continue
                else:
                    print(f"  [AssetEngine] No semantic matches for Brand ID {target_id}. Using fallback.")
            
            # --- STRATEGY 3: RANDOM LOCAL FALLBACK ---
            if db:
                # Intentar buscar cualquier cosa de la marca si lo semántico falló
                target_id = getattr(brand, "brand_id", brand.id) if brand else -1
                all_local = db.query(models.BrandAsset).filter(
                    models.BrandAsset.brand_id == target_id,
                    models.BrandAsset.category == "photos"
                ).all()
                
                if all_local:
                    chosen = random.choice(all_local)
                    asset_map[slide_idx] = chosen.local_path
                    print(f"  [AssetEngine] Random local fallback for Slide {slide_idx}")
                    continue
            
            # --- STRATEGY 4: LOGO FALLBACK ---
            if num_logos > 0:
                asset_map[slide_idx] = logos[0]
                continue
            
    if num_logos > 0:
        asset_map["global_logo"] = logos[0]

    return asset_map
