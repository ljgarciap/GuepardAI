"""
asset_library_service.py — PowerAI
Servicio especializado para la gestión de activos de marca (Biblioteca).
Deduplicación, Tagging Semántico y Categorización.
"""
import os
import hashlib
import json
from typing import List, Optional
from sqlalchemy.orm import Session
import models
from llm_provider import generate_vision_json

def get_file_hash(file_path: str) -> str:
    """Calcula el SHA-256 de un archivo para deduplicación."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def register_asset(db: Session, brand_id: Optional[int], file_path: str, 
                   category: str = "photos", force_tagging: bool = False,
                   is_public: bool = False, source_doc: Optional[str] = None,
                   manual_tags: List[str] = None) -> models.BrandAsset:
    """
    Registra un activo en la biblioteca con Gobernanza y Etiquetas Manuales.
    """
    f_hash = get_file_hash(file_path)
    filename = os.path.basename(file_path)
    
    # 1. Verificar duplicados (considerando visibilidad y marca)
    existing = db.query(models.BrandAsset).filter(
        models.BrandAsset.file_hash == f_hash
    )
    
    if not is_public:
        existing = existing.filter(models.BrandAsset.brand_id == brand_id)
    else:
        existing = existing.filter(models.BrandAsset.is_public == 1)
        
    existing_record = existing.first()
    
    if existing_record and not force_tagging:
        print(f"  [Library] Asset already exists (hash {f_hash[:8]}). Reusing.")
        return existing_record

    # 2. Análisis Semántico con Vision IA
    print(f"  [Library] Analyzing NEW asset: {filename} (Public: {is_public})...")
    tags = []
    description = "brand asset"
    
    try:
        prompt = """
        Analyze this brand asset image. 
        1. Categorize it: 'logo', 'icon', 'photo-subject', 'photo-background'.
        2. Give 5 semantic tags (e.g. 'retail', 'fresh', 'growth', 'abstract', 'technology').
        3. One-line description.
        Output ONLY JSON: {"category": "...", "tags": [...], "description": "..."}
        """
        res = generate_vision_json(prompt, [file_path])
        category = res.get("category", category)
        tags = res.get("tags", [])
        description = res.get("description", description)
    except Exception as e:
        print(f"  [Library] Tagging failed for {filename}: {e}")

    # 3. Guardar en DB con Gobernanza
    new_asset = models.BrandAsset(
        brand_id=brand_id if not is_public else None,
        file_hash=f_hash,
        local_path=file_path,
        category=category,
        tags=tags,
        manual_tags=manual_tags, # v11.0: User enrichment
        description=description,
        is_public=1 if is_public else 0,
        source_doc=source_doc
    )
    db.add(new_asset)
    db.commit()
    db.refresh(new_asset)
    
    return new_asset

def find_best_assets(db: Session, brand_id: int, keywords: List[str], 
                      category: Optional[str] = None, limit: int = 3) -> List[models.BrandAsset]:
    """
    Busca los mejores activos. 
    Lógica: (Marca específica OR Públicos) AND Categoría.
    """
    from sqlalchemy import or_
    query = db.query(models.BrandAsset).filter(
        or_(
            models.BrandAsset.brand_id == brand_id,
            models.BrandAsset.is_public == 1
        )
    )
    
    if category:
        query = query.filter(models.BrandAsset.category == category)
        
    all_assets = query.all()
    
    # Scoring semántico
    scored = []
    for a in all_assets:
        score = 0
        a_tags = [t.lower() for t in (a.tags or [])]
        for kw in keywords:
            if kw.lower() in a_tags:
                score += 1
        scored.append((score, a))
        
    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored[:limit]]
