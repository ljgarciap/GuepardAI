import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from database import Base


class Brand(Base):
    """
    MAESTRO DE MARCAS.
    El Directorio Oficial para evitar duplicados y errores de ortografía.
    """
    __tablename__ = "brands"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, unique=True, index=True, nullable=False) # "Castrol", "Tesco", etc.
    description = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=datetime.datetime.utcnow)

    # Relaciones
    visual_dna = relationship("BrandVisualDna", back_populates="brand", uselist=False)
    assets     = relationship("BrandAsset", back_populates="brand")


class BrandVisualDna(Base):
    __tablename__ = "brand_visual_dna"

    id               = Column(Integer, primary_key=True, index=True)
    brand_id         = Column(Integer, ForeignKey("brands.id"), unique=True)
    source_filename  = Column(String, index=True, nullable=False)
    
    brand = relationship("Brand", back_populates="visual_dna")
    assets = relationship("BrandAsset", back_populates="brand_dna") # legacy link if needed or remove

    # Paleta de colores
    primary_color    = Column(String, default="#000000")
    secondary_color  = Column(String, default="#404040")
    background_color = Column(String, default="#FFFFFF")
    text_main_color  = Column(String, default="#111111")
    accent_color     = Column(String, nullable=True)

    # Tipografía
    primary_font     = Column(String, default="Arial")
    secondary_font   = Column(String, nullable=True)

    # Assets físicos extraídos del documento (logos, imágenes de marca)
    # Lista de basenames: ["logo_abc.png", "brand_photo.jpg"]
    extracted_assets = Column(JSONB, nullable=True)

    # Captura completa del LLM para auditoría y debugging
    raw_extraction   = Column(JSONB, nullable=True)

    created_at       = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relación con la nueva Biblioteca de Activos
    assets = relationship("BrandAsset", back_populates="brand", cascade="all, delete-orphan")


class BrandAsset(Base):
    """
    Biblioteca de Activos Inteligente.
    """
    __tablename__ = "brand_assets"

    id = Column(Integer, primary_key=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=True) # Linked to Master Brand
    brand_dna_id = Column(Integer, ForeignKey("brand_visual_dna.id"), nullable=True) # Linked to specific DNA extraction
    
    file_hash = Column(String(64), index=True) 
    local_path = Column(String(512))
    
    category = Column(String(50)) 
    tags = Column(JSON)           # AI Generated Tags
    manual_tags = Column(JSON)    # USER Specified Tags (v11.0)
    description = Column(String(512))
    
    is_public = Column(Integer, default=0) 
    source_doc = Column(String(255))      

    metadata_json = Column(JSON) 
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    brand = relationship("Brand", back_populates="assets")
    brand_dna = relationship("BrandVisualDna")


# ============================================================
# TABLA NUEVA: brand_artistic_essence
# Extracción interpretativa: layouts, gestos de diseñador, composición
# Herramienta: Vision LLM (Claude Sonnet con visión)
# ============================================================
class BrandArtisticEssence(Base):
    __tablename__ = "brand_artistic_essence"

    id              = Column(Integer, primary_key=True, index=True)
    source_filename = Column(String, index=True, nullable=False)  # mismo archivo que BrandVisualDna

    # Arquetipos de layout por tipo de slide
    # {
    #   "title":      { "layout": "full-bleed-left", "logo_position": "top-right", ... },
    #   "data":       { "layout": "split-horizontal", "accent": "vertical-line", ... },
    #   "image":      { "treatment": "full-bleed-overlay-40", ... },
    #   "conclusion": { "layout": "centered-dark", ... }
    # }
    slide_archetypes   = Column(JSONB, nullable=True)
    structural_archetypes = Column(JSONB, nullable=True) # ADN Estructural (rejillas, columnas)

    # Gestos distintivos del diseñador
    # {
    #   "uses_glassmorphism": false,
    #   "uses_gradients": true,
    #   "corner_style": "sharp|rounded|pill",
    #   "shadow_style": "none|soft|hard",
    #   "image_overlay_opacity": 0.4,
    #   "accent_geometry": "vertical-line|horizontal-bar|dot|none",
    #   "accent_color_source": "primary|secondary|accent"
    # }
    design_gestures    = Column(JSONB, nullable=True)

    # Reglas de composición y espacio
    # {
    #   "logo_position": "top-right|top-left|bottom-right|bottom-left",
    #   "content_gravity": "left|center|right",
    #   "visual_density": "high|medium|low",
    #   "margin_style": "tight|balanced|airy",
    #   "image_role": "background|supporting|hero",
    #   "text_hierarchy": "high-contrast|minimalist|executive"
    # }
    composition_rules  = Column(JSONB, nullable=True)

    # Descripción en lenguaje natural del estilo (útil para el prompt de generación)
    art_direction_note = Column(Text, nullable=True)

    # Respuesta raw del Vision LLM por slide (para auditoría)
    raw_vision_response = Column(JSONB, nullable=True)

    created_at         = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at         = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


# ============================================================
# TABLA EXISTENTE: ingestion_jobs (actualizada)
# ingestion_type válidos: 'visual_dna' | 'artistic' | 'knowledge'
# ============================================================
class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id             = Column(Integer, primary_key=True, index=True)
    client_name    = Column(String, index=True)
    ingestion_type = Column(String, index=True)  # 'visual_dna' | 'artistic' | 'knowledge'

    status         = Column(String, default="pending")  # pending | processing | completed | error
    current_step   = Column(Text, default="Initialized.")
    progress       = Column(Integer, default=0)
    visibility_scope = Column(String(20), default="exclusive") # 'exclusive' | 'public'

    updated_at     = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


# ============================================================
# TABLA EXISTENTE: generation_jobs (sin cambios)
# ============================================================
class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id          = Column(Integer, primary_key=True, index=True)
    client_name = Column(String, index=True)
    brand_id    = Column(Integer, index=True)

    prompt      = Column(Text)              # Prompt original del usuario
    full_llm_prompt = Column(Text, nullable=True)  # Prompt final con contexto RAG
    llm_response_json = Column(JSONB, nullable=True) # JSON crudo devuelto por la IA

    status      = Column(String, default="pending")
    pptx_path   = Column(String, nullable=True)

    created_at  = Column(DateTime, default=datetime.datetime.utcnow)


# ============================================================
# TABLA LEGACY: brand_styles
# Mantenida temporalmente para no romper el flujo existente.
# Se eliminará una vez validado el nuevo flujo completo.
# ============================================================
class BrandStyle(Base):
    __tablename__ = "brand_styles"

    id               = Column(Integer, primary_key=True, index=True)
    client_name      = Column(String, index=True)
    style_slug       = Column(String, index=True, default="default")

    primary_color    = Column(String, default="#000000")
    secondary_color  = Column(String, default="#404040")
    background_color = Column(String, default="#FFFFFF")
    text_main_color  = Column(String, default="#111111")
    font_family      = Column(String, default="Arial")

    tone_description = Column(Text, default="Professional.")
    visual_patterns  = Column(JSON, nullable=True)
    visual_profile   = Column(String, default="modern")
    raw_style_json   = Column(JSON, nullable=True)
    extracted_assets = Column(JSON, nullable=True)
    visual_strategy  = Column(JSON, nullable=True)

    updated_at       = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
