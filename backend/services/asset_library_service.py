"""
asset_library_service.py — PowerAI
Servicio especializado para la gestión de activos de marca (Biblioteca).
Deduplicación, Tagging Semántico y Categorización Vectorial (v12.0).
"""
import os
import hashlib
import json
from typing import List, Optional
from sqlalchemy.orm import Session
import models
from llm_provider import generate_vision_json, get_embedding

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
    Ahora incluye generación de Embedding Semántico (v12.0).
    """
    f_hash = get_file_hash(file_path)
    filename = os.path.basename(file_path)
    
    # 1. Verificar duplicados
    existing = db.query(models.BrandAsset).filter(models.BrandAsset.file_hash == f_hash)
    if not is_public:
        existing = existing.filter(models.BrandAsset.brand_id == brand_id)
    else:
        existing = existing.filter(models.BrandAsset.is_public == 1)
        
    existing_record = existing.first()
    if existing_record and not force_tagging:
        print(f"  [Library] Asset already exists. Reusing.")
        return existing_record

    # 2. Análisis Semántico con Vision IA
    print(f"  [Library] Analyzing NEW asset: {filename}...")
    tags = []
    description = "brand asset"
    
    try:
        prompt = """
        Analyze this brand asset image for high-fidelity presentation use.
        1. Categorize it: 'logo', 'icon', 'photo-subject', 'photo-background'.
        2. Give 5-8 strategic semantic tags (e.g. 'growth', 'sustainability', 'executive').
        3. One-line professional description.
        Output ONLY JSON: {"category": "...", "tags": [...], "description": "..."}
        """
        res = generate_vision_json(prompt, [file_path])
        category = res.get("category", category)
        tags = res.get("tags", [])
        description = res.get("description", description)
    except Exception as e:
        print(f"  [Library] Tagging failed for {filename}: {e}")

    # 3. Generación de Embedding Semántico (Huella digital del activo)
    semantic_text = f"{description}. Keywords: {', '.join(tags)}"
    embedding = get_embedding(semantic_text)

    # 4. Guardar en DB
    new_asset = models.BrandAsset(
        brand_id=brand_id if not is_public else None,
        file_hash=f_hash,
        local_path=file_path,
        category=category,
        tags=tags,
        manual_tags=manual_tags,
        description=description,
        is_public=1 if is_public else 0,
        source_doc=source_doc,
        embedding=embedding
    )
    db.add(new_asset)
    db.commit()
    db.refresh(new_asset)
    
    return new_asset

def find_best_assets(db: Session, brand_id: int, keywords: List[str], 
                      category: Optional[str] = None, limit: int = 5,
                      exclude_ids: Optional[List[int]] = None) -> List[models.BrandAsset]:
    """
    Busca los mejores activos usando Búsqueda Vectorial Semántica (v12.0).
    """
    from sqlalchemy import or_
    
    # 1. Generar embedding de la búsqueda (la narrativa del slide)
    query_text = " ".join(keywords)
    query_embedding = None
    try:
        query_embedding = get_embedding(query_text)
    except Exception as e:
        print(f"  [AssetLibrary] Embedding failed: {e}. Falling back to simple query.")
    
    if not query_embedding:
        # Fallback a búsqueda simple si falla el embedding o no hay API Key
        print("  [AssetLibrary] Performing keyword-based fallback search.")
        query = db.query(models.BrandAsset).filter(
            or_(models.BrandAsset.brand_id == brand_id, models.BrandAsset.is_public == 1)
        )
        if category: query = query.filter(models.BrandAsset.category == category)
        if exclude_ids: query = query.filter(models.BrandAsset.id.not_in(exclude_ids))
        return query.limit(limit).all()

    # 2. Búsqueda Vectorial por Similitud Coseno (pgvector)
    # Primero intentamos con los de la MARCA
    sql_query = db.query(models.BrandAsset).filter(models.BrandAsset.brand_id == brand_id)
    if category: sql_query = sql_query.filter(models.BrandAsset.category == category)
    if exclude_ids: sql_query = sql_query.filter(models.BrandAsset.id.not_in(exclude_ids))
    
    results = sql_query.order_by(models.BrandAsset.embedding.cosine_distance(query_embedding)).limit(limit).all()
    
    if not results:
        # FALLBACK: Buscar en los activos PÚBLICOS/GLOBALES
        print(f"  [Library] No brand assets found for {brand_id}. Falling back to Global Library...")
        sql_global = db.query(models.BrandAsset).filter(models.BrandAsset.is_public == 1)
        if category: sql_global = sql_global.filter(models.BrandAsset.category == category)
        if exclude_ids: sql_global = sql_global.filter(models.BrandAsset.id.not_in(exclude_ids))
        results = sql_global.order_by(models.BrandAsset.embedding.cosine_distance(query_embedding)).limit(limit).all()
    
    return results
