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
from providers.llm_provider import generate_vision_json, get_embedding

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

    # 2. Semantic Analysis v19.0: VISION-FIRST Categorization
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
        config_record = db.query(models.SystemConfig).filter(models.SystemConfig.key == "prompt_classifier_v1").first()
        
        if config_record:
            vision_prompt = config_record.value
        else:
            vision_prompt = """Analyze this image and return a JSON object strictly following this schema:
{
  "category": "photos", 
  "description": "Breve descripción en español (max 15 palabras)",
  "tags": ["tag1", "tag2"]
}
RULES:
1. 'logos' category is STRICTLY for brand logos, wordmarks, or company identities (even if on transparent backgrounds).
2. Description MUST be in SPANISH and extremely short.
3. Tags must be in English or Spanish, lowercase, max 5 tags.
4. Never write huge paragraphs."""
            
        # CONTEXT-AWARE INJECTION (v23.0)
        # La instrucción de concisión se movió al seeder (prompt_classifier_v1)
        brand_name = "Unknown Brand"
        rulebook = ""
        if brand_id:
            brand_record = db.query(models.Brand).get(brand_id)
            if brand_record: brand_name = brand_record.name
            
            essence_record = db.query(models.BrandArtisticEssence).filter(models.BrandArtisticEssence.brand_id == brand_id).first()
            if essence_record and essence_record.art_direction_note:
                rulebook = essence_record.art_direction_note
                
        if brand_name != "Unknown Brand" or rulebook:
            vision_prompt += f"\n\nCRITICAL BRAND CONTEXT:\nYou are extracting assets for the brand '{brand_name}'. \n"
            vision_prompt += "DESIGNER GUIDELINE: Focus on composition and potential for creative layouts. If it is a clean object or fruit, it is a 'design_element'. If it is a person, identify their posture and background.\n"
            vision_prompt += f"Brand Rulebook Context: {rulebook[:1500]}"

            
        vision_res = generate_vision_json(vision_prompt, [file_path])
        
        # Respetar el logo manual, si no, usar lo que diga Visión
        if not is_explicit_logo:
            cat_val = vision_res.get("category", "lifestyle_photos")
            # Defensa contra LLM devolviendo objetos en lugar de strings (v19.2)
            if not isinstance(cat_val, str):
                cat_val = str(cat_val)
            final_category = cat_val.lower()
            
        tags = vision_res.get("tags", [])
        description = vision_res.get("description", description)
        
        # HEURÍSTICA DE SEGURIDAD (v61.0 - Anti-IA perezosa)
        desc_lower = description.lower()
        bg_type = vision_res.get("background_type", "other")
        is_isolated = any(sig in desc_lower for sig in ["isolated", "neutral background", "single object", "cut-out", "white background", "black background", "transparent"])
        is_human = vision_res.get("is_person", False)
        
        if not is_explicit_logo:
            if final_category != "logos":
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
        from services.assets.asset_intelligence import AssetIntelligence
        from providers.llm_provider import get_embeddings_batch
        with open(file_path, "rb") as f:
            image_bytes = f.read()
        try:
            embedding_fallback = get_embeddings_batch([image_bytes])[0]
            if embedding_fallback is None:
                category = "photos" # Default if embedding fails entirely (e.g. invalid bytes)
            else:
                intel = AssetIntelligence.categorize_by_similarity(embedding_fallback)
                category = intel["primary_category"]
        except Exception as embed_err:
            print(f"  [Library] Embedding fallback ALSO failed (likely 429 quota): {embed_err}")
            category = "photos"
            
    # RESTAURAR LOGO: Si era un logo explícito, la categoría forzada NUNCA debe sobreescribirse.
    if is_explicit_logo:
        category = "logos"

    # 3. Generar Embedding para Búsqueda (v4.0 - Coherencia Vectorial)
    # IMPORTANTE: Generamos el embedding del TEXTO descriptivo (Mistral 1024)
    # para asegurar que coincida con el espacio vectorial del buscador.
    from providers.llm_provider import get_embedding
    try:
        embedding = get_embedding(description)
    except Exception as e:
        print(f"  [Library] Text embedding failed (likely 429 quota): {e}")
        embedding = None

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
                      exclude_ids: Optional[List[int]] = None) -> List[tuple]:
    """
    Busca los mejores activos usando Búsqueda Vectorial Semántica (v4.0).
    Devuelve lista de tuplas (Asset, Score).
    """
    from sqlalchemy import or_, text
    
    # 1. Generar embedding de la búsqueda (la narrativa del slide)
    query_text = " ".join(keywords)
    query_embedding = None
    try:
        from providers.llm_provider import get_embedding
        query_embedding = get_embedding(query_text)
    except Exception as e:
        print(f"  [AssetLibrary] Embedding failed: {e}. Falling back to simple query.")
    
    if not query_embedding:
        # Fallback a búsqueda simple (Score 0.5 por defecto)
        query = db.query(models.BrandAsset).filter(
            or_(models.BrandAsset.brand_id == brand_id, models.BrandAsset.is_public == 1)
        ).filter(models.BrandAsset.category != "noise")
        if category: query = query.filter(models.BrandAsset.category == category)
        if exclude_ids: query = query.filter(models.BrandAsset.id.not_in(exclude_ids))
        return [(a, 0.5) for a in query.limit(limit).all()]

    # 2. Búsqueda Vectorial por Similitud (pgvector)
    # Calculamos 1 - distancia para obtener similitud (0.0 a 1.0)
    sql_query = db.query(
        models.BrandAsset,
        (1.0 - models.BrandAsset.embedding.cosine_distance(query_embedding)).label("score")
    ).filter(
        or_(models.BrandAsset.brand_id == brand_id, models.BrandAsset.is_public == 1)
    ).filter(models.BrandAsset.category != "noise")
    
    if category: sql_query = sql_query.filter(models.BrandAsset.category == category)
    if exclude_ids: sql_query = sql_query.filter(models.BrandAsset.id.not_in(exclude_ids))
    
    # We get top 10 candidates first, then filter visually
    raw_results = sql_query.order_by(text("score DESC")).limit(max(10, limit * 2)).all()
    
    # --- FASE 6: LOCAL VISION RERANKING ---
    # HOTFIX: Disabled because calling Pixtral Vision for 10 images per slide (150+ calls)
    # causes the generation pipeline to hang for 15+ minutes.
    # Semantic text vector search (pgvector) is sufficient for asset matching.
    return [(r[0], float(r[1]) if r[1] is not None else 0.5) for r in raw_results[:limit]]

def find_assets_by_tags(db: Session, brand_id: int, tags: List[str], min_matches: int = 2, limit: int = 5, exclude_ids: Optional[List[int]] = None) -> List[tuple]:
    """
    Busca activos que coincidan con etiquetas (v5.9 - Brand-Aware Tokenized).
    """
    brand_name = "Unknown"
    brand_rec = db.query(models.Brand).get(brand_id)
    if brand_rec: brand_name = brand_rec.name.lower()

    query = db.query(models.BrandAsset).filter(
        models.BrandAsset.brand_id == brand_id,
        models.BrandAsset.category != "noise"
    )
    if exclude_ids:
        query = query.filter(models.BrandAsset.id.not_in(exclude_ids))

    all_assets = query.all()
    results = []
    
    # Tokenizar las etiquetas de búsqueda
    search_tokens = set()
    for t in tags:
        for word in t.lower().replace(",", " ").replace("-", " ").split():
            if len(word) > 2: search_tokens.add(word)
    
    print(f"  [LibraryAudit] Target Tokens: {list(search_tokens)}")
    
    for asset in all_assets:
        # Tokenizar etiquetas del activo
        a_tags = (asset.tags or []) + (asset.manual_tags or [])
        asset_tokens = set()
        for t in a_tags:
            for word in str(t).lower().replace(",", " ").replace("-", " ").split():
                if len(word) > 2: asset_tokens.add(word)
        
        asset_tokens.add(brand_name)
        
        intersection = search_tokens.intersection(asset_tokens)
        if len(intersection) > 0:
            print(f"    - Asset {asset.id}: Found {len(intersection)} matches {list(intersection)}")
            
        if len(intersection) >= min_matches:
            score = 0.5 + (len(intersection) * 0.1)
            results.append((asset, min(0.98, score)))

    if not results:
        print(f"  [LibraryAudit] No assets met the minimum of {min_matches} matches.")
    
    # Ordenar y limitar
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:limit]
