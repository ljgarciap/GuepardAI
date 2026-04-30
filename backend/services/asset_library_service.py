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
                   manual_tags: List[str] = None,
                   width: Optional[int] = None, height: Optional[int] = None) -> models.BrandAsset:
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

    # 2. Análisis Semántico v19.0: VISION-FIRST Categorization
    print(f"  [Library] Analyzing NEW asset with VISION: {filename}...")
    
    # 2.1 Visión para Identidad y Categoría Real
    tags = []
    description = f"Brand asset: {filename}"
    
    # PROTECCIÓN DE LOGO (v23.0)
    # Si la categoría viene explícita como logo desde la subida manual, la protegemos.
    is_explicit_logo = category in ["logo", "logos"]
    final_category = "logos" if is_explicit_logo else "photos"
    
    try:
        # Carga dinámica del Prompt desde la DB (v19.1)
        from database import SessionLocal
        db_session = SessionLocal()
        config_record = db_session.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_classifier_v1").first()
        db_session.close()
        
        if config_record:
            vision_prompt = config_record.value
        else:
            vision_prompt = "Analyze this image and return category, description and tags."
            
        # CONTEXT-AWARE INJECTION (v23.0)
        # La instrucción de concisión se movió al seeder (prompt_classifier_v1)
        brand_name = "Unknown Brand"
        rulebook = ""
        if brand_id:
            brand_record = db_session.query(models.Brand).get(brand_id)
            if brand_record: brand_name = brand_record.name
            
            essence_record = db_session.query(models.BrandArtisticEssence).filter(models.BrandArtisticEssence.brand_id == brand_id).first()
            if essence_record and essence_record.art_direction_note:
                rulebook = essence_record.art_direction_note
                
        if brand_name != "Unknown Brand" or rulebook:
            vision_prompt += f"\n\nCRITICAL BRAND CONTEXT:\nYou are extracting assets for the brand '{brand_name}'. Do NOT classify competitor logos as 'logos', classify them as 'design_elements' or 'noise'.\nBrand Rulebook Context: {rulebook[:1500]}"

            
        vision_res = generate_vision_json(vision_prompt, [file_path])
        
        # Respetar el logo manual, si no, usar lo que diga Visión
        if not is_explicit_logo:
            final_category = vision_res.get("category", "lifestyle_photos").lower()
            
        tags = vision_res.get("tags", [])
        description = vision_res.get("description", description)
        
        # HEURÍSTICA DE SEGURIDAD (v61.0 - Anti-IA perezosa)
        desc_lower = description.lower()
        bg_type = vision_res.get("background_type", "other")
        is_isolated = any(sig in desc_lower for sig in ["isolated", "neutral background", "single object", "cut-out", "white background", "black background", "transparent"])
        is_human = vision_res.get("is_person", False)
        
        if not is_explicit_logo:
            if final_category in ["photos", "lifestyle_photos"] or bg_type in ["solid_white", "solid_black", "transparent"]:
                # EXCEPCIÓN: Si es una persona aislada, NO es un elemento de diseño, es lifestyle
                if is_isolated and not is_human:
                    print(f"  [Library] HEURISTIC TRIGGERED: Re-mapping {final_category} -> design_elements for {filename}")
                    final_category = "design_elements"

        # Ajuste por contenido humano (v28.0)
        if is_human:
            tags.extend(["human", "people", "lifestyle", "professional"])
            if final_category == "logos" and not is_explicit_logo: 
                final_category = "lifestyle_photos"
                
        category = final_category
            
    except Exception as e:
        print(f"  [Library] Vision failed, falling back to similarity: {e}")
        # Fallback a similitud solo si Visión falla
        from services.asset_intelligence import AssetIntelligence
        from llm_provider import get_embeddings_batch
        with open(file_path, "rb") as f:
            image_bytes = f.read()
        embedding_fallback = get_embeddings_batch([image_bytes])[0]
        intel = AssetIntelligence.categorize_by_similarity(embedding_fallback)
        category = intel["primary_category"]

    # 3. Generar Embedding para Búsqueda (Independiente de la categoría)
    from llm_provider import get_embeddings_batch
    with open(file_path, "rb") as f:
        image_bytes = f.read()
    embedding = get_embeddings_batch([image_bytes])[0]

    # 4. Guardar en DB
    new_asset = models.BrandAsset(
        brand_id=brand_id if not is_public else None,
        file_hash=f_hash,
        local_path=file_path,
        category=category,
        tags=tags,
        manual_tags=manual_tags,
        description=description,
        width=width,
        height=height,
        is_public=1 if is_public else 0,
        source_doc=source_doc,
        embedding=embedding
    )
    db.add(new_asset)
    db.flush()
    db.refresh(new_asset)
    print(f"  [Library] Asset REGISTERED: ID={new_asset.id}, Category={new_asset.category}, Hash={f_hash[:8]}")
    
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
        ).filter(models.BrandAsset.category != "noise") # EXCLUDE NOISE
        if category: query = query.filter(models.BrandAsset.category == category)
        if exclude_ids: query = query.filter(models.BrandAsset.id.not_in(exclude_ids))
        return query.limit(limit).all()

    # 2. Búsqueda Vectorial por Similitud Coseno (pgvector)
    # Primero intentamos con los de la MARCA
    sql_query = db.query(models.BrandAsset).filter(models.BrandAsset.brand_id == brand_id).filter(models.BrandAsset.category != "noise")
    if category: sql_query = sql_query.filter(models.BrandAsset.category == category)
    if exclude_ids: sql_query = sql_query.filter(models.BrandAsset.id.not_in(exclude_ids))
    
    results = sql_query.order_by(models.BrandAsset.embedding.cosine_distance(query_embedding)).limit(limit).all()
    
    if not results:
        # FALLBACK: Buscar en los activos PÚBLICOS/GLOBALES
        print(f"  [Library] No brand assets found for {brand_id}. Falling back to Global Library...")
        sql_global = db.query(models.BrandAsset).filter(models.BrandAsset.is_public == 1).filter(models.BrandAsset.category != "noise")
        if category: sql_global = sql_global.filter(models.BrandAsset.category == category)
        if exclude_ids: sql_global = sql_global.filter(models.BrandAsset.id.not_in(exclude_ids))
        results = sql_global.order_by(models.BrandAsset.embedding.cosine_distance(query_embedding)).limit(limit).all()
    
    return results
