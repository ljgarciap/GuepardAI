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

def register_asset(db: Session, brand_id: int, file_path: str, 
                   category: str = "photos", force_tagging: bool = False) -> models.BrandAsset:
    """
    Registra un activo en la biblioteca.
    Si el hash existe, retorna el registro actual.
    Si no, usa Vision para etiquetarlo y lo guarda.
    """
    f_hash = get_file_hash(file_path)
    filename = os.path.basename(file_path)
    
    # 1. Verificar duplicados para esta marca
    existing = db.query(models.BrandAsset).filter(
        models.BrandAsset.brand_id == brand_id,
        models.BrandAsset.file_hash == f_hash
    ).first()
    
    if existing and not force_tagging:
        print(f"  [Library] Asset already exists (hash {f_hash[:8]}). Reusing.")
        return existing

    # 2. Análisis Semántico con Vision (Solo si es nuevo o forzado)
    print(f"  [Library] Analyzing NEW asset: {filename}...")
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

    # 3. Guardar en DB
    new_asset = models.BrandAsset(
        brand_id=brand_id,
        file_hash=f_hash,
        local_path=file_path,
        category=category,
        tags=tags,
        description=description
    )
    db.add(new_asset)
    db.commit()
    db.refresh(new_asset)
    
    return new_asset

def find_best_assets(db: Session, brand_id: int, keywords: List[str], 
                     category: Optional[str] = None, limit: int = 3) -> List[models.BrandAsset]:
    """
    Busca los mejores activos basados en palabras clave (tags).
    """
    query = db.query(models.BrandAsset).filter(models.BrandAsset.brand_id == brand_id)
    if category:
        query = query.filter(models.BrandAsset.category == category)
        
    all_assets = query.all()
    # Scoring simple por coincidencia de tags
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
