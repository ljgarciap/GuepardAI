import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from database import Base


class Brand(Base):
    """
    MAESTRO DE MARCAS (Directorio Oficial).
    Contiene la metadata estratégica que guía el tono de la IA.
    """
    __tablename__ = "brands"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, unique=True, index=True, nullable=False)
    logo_path   = Column(String, nullable=True) # Logo oficial de referencia
    about       = Column(Text, nullable=True)      # Resumen estratégico / Quiénes somos
    core_value  = Column(String, nullable=True)  # Valor central / Slogan
    
    created_at  = Column(DateTime, default=datetime.datetime.utcnow)

    # Relaciones
    visual_dna = relationship("BrandVisualDna", back_populates="brand")
    artistic_essence = relationship("BrandArtisticEssence", back_populates="brand")
    assets     = relationship("BrandAsset", back_populates="brand")
    knowledge  = relationship("CorporateKnowledge", back_populates="brand")


class BrandVisualDna(Base):
    __tablename__ = "brand_visual_dna"

    id               = Column(Integer, primary_key=True, index=True)
    brand_id         = Column(Integer, ForeignKey("brands.id"))
    source_filename  = Column(String, index=True, nullable=False)
    
    brand = relationship("Brand", back_populates="visual_dna")
    
    # Paleta de colores
    primary_color    = Column(String, default="#000000")
    secondary_color  = Column(String, default="#404040")
    background_color = Column(String, default="#FFFFFF")
    text_main_color  = Column(String, default="#111111")
    accent_color     = Column(String, nullable=True)

    # Tipografía
    primary_font     = Column(String, default="Arial")
    secondary_font   = Column(String, nullable=True)

    # Assets físicos extraídos del documento
    extracted_assets = Column(JSONB, nullable=True)

    # Captura completa del LLM para auditoría
    raw_extraction   = Column(JSONB, nullable=True)

    # Dimensiones físicas del slide original (v12.5)
    slide_width_inches   = Column(Float, default=13.33)
    slide_height_inches  = Column(Float, default=7.5)

    created_at       = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    is_public        = Column(Integer, default=0) # 0=Exclusive, 1=Public


class BrandAsset(Base):
    """
    Biblioteca de Activos Inteligente.
    """
    __tablename__ = "brand_assets"

    id = Column(Integer, primary_key=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=True) # Linked to Master Brand
    brand_dna_id = Column(Integer, ForeignKey("brand_visual_dna.id"), nullable=True) # Linked to specific DNA extraction
    
    file_hash = Column(String(64), index=True) 
    local_path = Column(String(1024))
    
    category = Column(String(50)) 
    tags = Column(JSON)           # AI Generated Tags
    manual_tags = Column(JSON)    # USER Specified Tags (v11.0)
    description = Column(Text)
    
    is_public = Column(Integer, default=0) 
    source_doc = Column(String(512))      

    metadata_json = Column(JSON) 
    embedding = Column(Vector(1024), nullable=True) # Vector representation for semantic search
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
    brand_id        = Column(Integer, ForeignKey("brands.id"))
    source_filename = Column(String, index=True, nullable=False)  # mismo archivo que BrandVisualDna

    brand = relationship("Brand", back_populates="artistic_essence")

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
    is_public          = Column(Integer, default=0) # 0=Exclusive, 1=Public


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
    current_step = Column(String, nullable=True) # v12.0: Para logs en tiempo real
    progress    = Column(Integer, default=0)    # v12.0: Porcentaje de avance
    pptx_path   = Column(String, nullable=True)

    created_at  = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relación con las slides granulares (v18.5)
    slides      = relationship("PresentationSlide", back_populates="job", cascade="all, delete-orphan")


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

class Language(Base):
    __tablename__ = "languages"

    id           = Column(Integer, primary_key=True, index=True)
    code         = Column(String(10), unique=True, index=True) # e.g., 'UK', 'USA', 'LATAM'
    name         = Column(String(50), nullable=False)          # e.g., 'English (UK)'
    priority     = Column(Integer, default=100)                # For custom ordering
    is_active    = Column(Boolean, default=True)

    created_at   = Column(DateTime, default=datetime.datetime.utcnow)


class CorporateKnowledge(Base):
    """
    BANCO DE CONOCIMIENTO (RAG).
    Datos estratégicos blindados por marca.
    """
    __tablename__ = "corporate_knowledge"

    id = Column(Integer, primary_key=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=True)
    
    source_filename = Column(String(255))
    content = Column(Text)
    
    # Taxonomía: brand_identity, company_knowledge, case_studies, etc.
    document_type = Column(String(50), nullable=True)
    
    # Metadata para RAG y Embeddings (v12.0)
    meta_data = Column(JSONB, nullable=True)
    embedding = Column(Vector(1024), nullable=True) # Mistral-embed standard
    
    # is_public: 0 = Exclusive, 1 = Public
    is_public = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relación inversa
    brand = relationship("Brand", back_populates="knowledge")

class PresentationSlide(Base):
    """
    ESTADO ATÓMICO DE SLIDE (v18.5).
    Guarda la decisión final del Director de Arte para cada diapositiva.
    """
    __tablename__ = "presentation_slides"

    id           = Column(Integer, primary_key=True, index=True)
    job_id       = Column(Integer, ForeignKey("generation_jobs.id"))
    
    slide_number = Column(Integer)
    title        = Column(String(500))
    content_json = Column(JSONB) # { "bullets": [...], "subtitle": "..." }
    
    # Decisiones del Director de Arte
    layout_slug  = Column(String(100)) # 'split-right', 'full-bleed', etc.
    assigned_image = Column(String(500), nullable=True)
    reference_id = Column(Integer, nullable=True) # ID del asset de referencia (v18.7)
    font_scale   = Column(Float, default=1.0)
    
    # Elementos finales renderizables (v18.5)
    # Lista de diccionarios con coordenadas y estilos finales
    render_elements = Column(JSONB, nullable=True) 

    job = relationship("GenerationJob", back_populates="slides")

class SystemConfig(Base):
    """
    TABLA PARAMÉTRICA (v18.1).
    Evita el hardcodeo de modelos y límites del sistema.
    """
    __tablename__ = "system_configs"

    id    = Column(Integer, primary_key=True, index=True)
    key   = Column(String(100), unique=True, index=True, nullable=False)
    value = Column(String(500), nullable=False)
    description = Column(String(255), nullable=True)
    updated_at  = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
