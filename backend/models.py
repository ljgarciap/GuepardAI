import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Float, ForeignKey, Boolean, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from database import Base


class IngestionJobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSING_VISUAL_DNA = "processing_visual_dna"
    VISUAL_DNA_EXTRACTED = "visual_dna_extracted"
    PROCESSING_ARTISTIC_ESSENCE = "processing_artistic_essence"
    ARTISTIC_ESSENCE_EXTRACTED = "artistic_essence_extracted"
    COMPLETED = "completed"
    ERROR = "error"


class GenerationJobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SYNTHESIZING_CONTENT = "synthesizing_content"
    CONTENT_READY = "content_ready"
    PLANNING_DESIGN = "planning_design"
    DESIGN_PLANNED = "design_planned"
    QA_FAILED = "qa_failed"
    QA_PASSED = "qa_passed"
    COMPLETED = "completed"
    ERROR = "error"


class PresentationSlideStatus(str, Enum):
    PENDING = "pending"
    CONTENT_READY = "content_ready"
    PLANNED = "planned"
    RENDERED = "rendered"


class UserRole(str, Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    CLIENTE = "cliente"


# ============================================================
# Autenticación, Roles Multi-Usuario y Base Multi-Tenant
# Tenant = límite de propiedad por encima de Brand (1 tenant -> N brands).
# Spec: docs/specs/autenticacion-multiusuario-multitenant.md
# Design: docs/designs/autenticacion-multitenant-design.md
# ============================================================
class Tenant(Base):
    __tablename__ = "tenants"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, nullable=False)
    is_active  = Column(Integer, default=1)  # 0/1, convención del proyecto
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    users  = relationship("User", back_populates="tenant")
    brands = relationship("Brand", back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role            = Column(String, nullable=False)  # valor de UserRole
    tenant_id       = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)  # null solo para superadmin
    is_active       = Column(Integer, default=1)
    # Asignación opcional (reviews-analitica-colaboracion, ítem 4) — no bloquea registro de usuarios existentes.
    department_id   = Column(Integer, ForeignKey("departments.id"), nullable=True)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)

    tenant = relationship("Tenant", back_populates="users")
    department = relationship("Department")


class Department(Base):
    """Catálogo de departamentos administrado por tenant (reviews-analitica-colaboracion, ítem 4)."""
    __tablename__ = "departments"

    id         = Column(Integer, primary_key=True, index=True)
    tenant_id  = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    name       = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    tenant = relationship("Tenant")

    __table_args__ = (UniqueConstraint('tenant_id', 'name', name='uq_department_tenant_name'),)

    @property
    def tenant_name(self) -> Optional[str]:
        return self.tenant.name if self.tenant else None


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
    tenant_id   = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)  # Autenticación/Multi-tenant

    created_at  = Column(DateTime, default=datetime.datetime.utcnow)

    # Relaciones
    tenant     = relationship("Tenant", back_populates="brands")
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
    secondary_color  = Column(String, default="#EE1C2E")
    background_color = Column(String, default="#FFFFFF")
    text_main_color  = Column(String, default="#111111")
    text_on_dark     = Column(String, default="#FFFFFF") # Nueva columna para contraste
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
    # Hash perceptual dHash 64-bit (Calidad Selección v2): duplicados VISUALES
    # (misma foto a distintas resoluciones). Null = pendiente de backfill.
    perceptual_hash = Column(String(32), index=True, nullable=True)
    local_path = Column(String(1024))
    
    category = Column(String(50)) 
    tags = Column(JSON)           # AI Generated Tags
    manual_tags = Column(JSON)    # USER Specified Tags (v11.0)
    description = Column(Text)
    
    # Real physical dimensions (v34.0 - Anti-Stretching)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)

    # Perfil visual estructurado del Vision LLM (Selección de Imágenes v1)
    # {orientation, dominant_colors, composition: {subject_position, negative_space}, layout_suitability}
    visual_profile = Column(JSON, nullable=True)

    is_public = Column(Integer, default=0)
    source_doc = Column(String(512))      

    metadata_json = Column(JSON) 
    embedding = Column(Vector(1024), nullable=True) # Vector representation for semantic search
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    brand = relationship("Brand", back_populates="assets")
    brand_dna = relationship("BrandVisualDna")


# ============================================================
# TABLA NUEVA: brand_artistic_essence
# Extraction interpretativa: layouts, gestos de diseñador, composición
# Tool: Vision LLM (Claude Sonnet con visión)
# ============================================================
class BrandArtisticEssence(Base):
    __tablename__ = "brand_artistic_essence"

    id              = Column(Integer, primary_key=True, index=True)
    brand_id        = Column(Integer, ForeignKey("brands.id"))
    source_filename = Column(String, index=True, nullable=False)  # mismo archivo que BrandVisualDna

    brand = relationship("Brand", back_populates="artistic_essence")
    
    # Estrategia visual general (extraída por Vision)
    visual_strategy = Column(JSON, nullable=True)

    # Arquetipos de layout por tipo de slide
    # {
    #   "title":      { "layout": "full-bleed-left", "logo_position": "top-right", ... },
    #   "data":       { "layout": "split-horizontal", "accent": "vertical-line", ... },
    #   "image":      { "treatment": "full-bleed-overlay-40", ... },
    #   "conclusion": { "layout": "centered-dark", ... }
    # }
    slide_archetypes   = Column(JSON, nullable=True)
    structural_archetypes = Column(JSON, nullable=True) # ADN Estructural (rejillas, columnas)

    # Gestures distintivos del diseñador
    # {
    #   "uses_glassmorphism": false,
    #   "uses_gradients": true,
    #   "corner_style": "sharp|rounded|pill",
    #   "shadow_style": "none|soft|hard",
    #   "image_overlay_opacity": 0.4,
    #   "accent_geometry": "vertical-line|horizontal-bar|dot|none",
    #   "accent_color_source": "primary|secondary|accent"
    # }
    design_gestures    = Column(JSON, nullable=True)

    # Rules de composición y espacio
    # {
    #   "logo_position": "top-right|top-left|bottom-right|bottom-left",
    #   "content_gravity": "left|center|right",
    #   "visual_density": "high|medium|low",
    #   "margin_style": "tight|balanced|airy",
    #   "image_role": "background|supporting|hero",
    #   "text_hierarchy": "high-contrast|minimalist|executive"
    # }
    composition_rules  = Column(JSON, nullable=True)

    # Description en lenguaje natural del estilo (útil para el prompt de generación)
    art_direction_note = Column(Text, nullable=True)

    # Response raw del Vision LLM por slide (para auditoría)
    raw_vision_response = Column(JSONB, nullable=True)

    created_at         = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at         = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    is_public          = Column(Integer, default=0) # 0=Exclusive, 1=Public


class BrandPremiumVisualPattern(Base):
    """
    Premium Visual Agent pattern store.
    Keeps executable visual patterns separate from BrandVisualDna so the PPTX
    pipeline can continue using its existing brand DNA contract.
    """
    __tablename__ = "brand_premium_visual_patterns"

    id              = Column(Integer, primary_key=True, index=True)
    brand_id        = Column(Integer, ForeignKey("brands.id"), index=True)
    source_filename = Column(String, index=True, nullable=False)

    patterns_json   = Column(JSONB, nullable=True)
    pattern_summary = Column(Text, nullable=True)
    raw_extraction  = Column(JSONB, nullable=True)

    created_at      = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


# ============================================================
# TABLA EXISTENTE: ingestion_jobs (actualizada)
# ingestion_type valid: 'visual_dna' | 'artistic' | 'knowledge'
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
    style_id    = Column(Integer, nullable=True) # v23.0: Enlace al Blueprint/Dna elegido

    prompt      = Column(Text)              # Prompt original del usuario
    full_llm_prompt = Column(Text, nullable=True)  # Prompt final con contexto RAG
    llm_response_json = Column(JSONB, nullable=True) # JSON crudo devuelto por la IA
    # Selección estructurada del compositor guiado (soporte-indicaciones): categoría de
    # intención, tono, audiencia, tipo de slide, historia, reglas visuales, formato de
    # salida, flag "sin buzzwords". Nunca se usa para lógica de negoción — el campo
    # `prompt` de texto plano sigue siendo la única entrada real al pipeline.
    prompt_metadata = Column(JSONB, nullable=True)

    status      = Column(String, default="pending")
    current_step = Column(String, nullable=True) # v12.0: Para logs en tiempo real
    progress    = Column(Integer, default=0)    # v12.0: Porcentaje de avance
    allow_ai_images = Column(Boolean, default=False) # v7.0: Permiso para generar con Gemini
    qa_forced   = Column(Integer, default=0)    # F4 fixes-resiliencia: 1 si QA agotó reintentos y se forzó el pase
    display_name = Column(String(120), nullable=True)  # Etiqueta visible editable (Gestión de Portfolios); null → basename del archivo
    pptx_path   = Column(String, nullable=True)
    # Ownership y colaboración (reviews-analitica-colaboracion). Nullable: jobs
    # históricos no tienen owner conocido — no se hace backfill, gap aceptado.
    owner_id    = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at  = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationship con las slides granulares (v18.5)
    slides      = relationship("PresentationSlide", back_populates="job", cascade="all, delete-orphan")
    collaborators = relationship("GenerationJobCollaborator", back_populates="job", cascade="all, delete-orphan")
    reviews       = relationship("PresentationReview", back_populates="job", cascade="all, delete-orphan")


class GenerationJobCollaborator(Base):
    """Colaboradores invitados a un GenerationJob (además del owner)."""
    __tablename__ = "generation_job_collaborators"

    id         = Column(Integer, primary_key=True, index=True)
    job_id     = Column(Integer, ForeignKey("generation_jobs.id"), nullable=False)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    added_at   = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (UniqueConstraint('job_id', 'user_id', name='uq_job_collaborator'),)

    job  = relationship("GenerationJob", back_populates="collaborators")
    user = relationship("User")


class PresentationReview(Base):
    """Review + rating (1-5) de un colaborador sobre un GenerationJob."""
    __tablename__ = "presentation_reviews"

    id          = Column(Integer, primary_key=True, index=True)
    job_id      = Column(Integer, ForeignKey("generation_jobs.id"), nullable=False)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating      = Column(Integer, nullable=False)  # 1-5, CHECK agregado vía ALTER en database.py
    comment     = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    is_deleted  = Column(Boolean, default=False)
    moderation_status = Column(String(20), default="visible")  # visible | flagged | hidden

    __table_args__ = (
        UniqueConstraint('job_id', 'user_id', name='uq_job_review'),
        CheckConstraint('rating BETWEEN 1 AND 5', name='ck_review_rating_range'),
    )

    job  = relationship("GenerationJob", back_populates="reviews")
    user = relationship("User")




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
    Armored strategic data por marca.
    """
    __tablename__ = "corporate_knowledge"

    id = Column(Integer, primary_key=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=True)
    
    source_filename = Column(String(255))
    content = Column(Text)
    
    # Taxonomy: brand_identity, company_knowledge, case_studies, etc.
    document_type = Column(String(50), nullable=True)
    
    # Metadata para RAG y Embeddings (v12.0)
    meta_data = Column(JSONB, nullable=True)
    embedding = Column(Vector(1024), nullable=True) # Mistral-embed standard
    
    # is_public: 0 = Exclusive, 1 = Public
    is_public = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationship inversa
    brand = relationship("Brand", back_populates="knowledge")

class PresentationSlide(Base):
    """
    ESTADO ATÓMICO DE SLIDE (v18.5).
    Saves final decision del Director de Arte para cada diapositiva.
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
    
    # Estados de flujo v23.0
    status       = Column(String(50), default="pending") # pending | content_ready | planned | rendered
    qa_retry_count = Column(Integer, default=0)  # retries consumed for this slide
    qa_forced    = Column(Integer, default=0)    # 1 when retries exhausted; slide accepted as-is
    planning_json = Column(JSONB, nullable=True) # Decisiones de IA Art Director
    
    # Elementos finales renderizables (v18.5)
    # Lista de diccionarios con coordenadas y estilos finales
    render_elements = Column(JSONB, nullable=True) 

    job = relationship("GenerationJob", back_populates="slides")

    @property
    def background_asset_path(self):
        if self.planning_json and isinstance(self.planning_json, dict):
            return self.planning_json.get("background_asset_path")
        return None

    @background_asset_path.setter
    def background_asset_path(self, value):
        if not self.planning_json:
            self.planning_json = {}
        current = dict(self.planning_json)
        current["background_asset_path"] = value
        self.planning_json = current

class ArtDirectorDecision(Base):
    """
    BITÁCORA DE DECISIONES (v34.0).
    Records the 'porqué' de cada visual choice.
    """
    __tablename__ = "art_director_decisions"

    id           = Column(Integer, primary_key=True, index=True)
    job_id       = Column(Integer, ForeignKey("generation_jobs.id"))
    slide_number = Column(Integer)
    
    decision_type = Column(String(50)) # 'layout', 'asset_selection', 'color_logic'
    summary       = Column(Text)
    reasoning     = Column(Text)
    
    # Bitácora de Auditoría (v4.0)
    prompt_used  = Column(Text, nullable=True)
    response_raw = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    
    created_at   = Column(DateTime, default=datetime.datetime.utcnow)

    job = relationship("GenerationJob")

class SystemConfig(Base):
    """
    TABLA PARAMÉTRICA (v18.1).
    Evita el hardcodeo de modelos y límites del sistema.
    """
    __tablename__ = "system_configs"

    id    = Column(Integer, primary_key=True, index=True)
    key   = Column(String(100), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=False)
    description = Column(String(255), nullable=True)
    updated_at  = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class DataAlignment(Base):
    """
    ALINEACIONES DE DATOS (Iteración Alineaciones v1).
    Registro de procesos de convergencia de datos post-deploy (la tercera capa
    junto al esquema y la config). Estados: pending | running | done | failed.
    """
    __tablename__ = "data_alignments"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(120), unique=True, index=True, nullable=False)
    status      = Column(String(20), default="pending", index=True)
    detail      = Column(Text, nullable=True)
    started_at  = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at  = Column(DateTime, default=datetime.datetime.utcnow)


class UserActivityEvent(Base):
    """
    Analítica de producto por usuario (reviews-analitica-colaboracion, ítem 5).
    Distinto de PerformanceMetric (esa es telemetría de sistema — duración de
    llamadas LLM/pipeline). Tabla genérica única para ambas métricas (ediciones
    + tiempo invertido) — evita dos tablas casi idénticas.
    """
    __tablename__ = "user_activity_events"

    id         = Column(Integer, primary_key=True, index=True)
    job_id     = Column(Integer, ForeignKey("generation_jobs.id"), nullable=False)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_type = Column(String(30), nullable=False)  # 'slide_edit' | 'session_time_seconds'
    value      = Column(Integer, nullable=False, default=1)  # 1 para slide_edit, segundos para session_time
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class UsageReport(Base):
    """
    Reporte mensual de uso (reviews-analitica-colaboracion, ítem 7). Uno por
    tenant + uno global (tenant_id NULL, solo superadmin) por cada período.
    """
    __tablename__ = "usage_reports"

    id           = Column(Integer, primary_key=True, index=True)
    tenant_id    = Column(Integer, ForeignKey("tenants.id"), nullable=True)  # NULL = plataforma completa
    period_start = Column(DateTime, nullable=False)
    period_end   = Column(DateTime, nullable=False)
    payload_json = Column(JSONB, nullable=False)
    created_at   = Column(DateTime, default=datetime.datetime.utcnow)
    sent_at      = Column(DateTime, nullable=True)


class PerformanceMetric(Base):
    """
    REGISTRO DE MÉTRICAS DE RENDIMIENTO (observabilidad).
    Guarda los tiempos de ejecución de herramientas, llamadas a LLM, y pipelines.
    """
    __tablename__ = "performance_metrics"

    id               = Column(Integer, primary_key=True, index=True)
    event_name       = Column(String(100), index=True, nullable=False)
    duration_seconds = Column(Float, nullable=False)
    metadata_json    = Column(JSONB, nullable=True)
    
    timestamp        = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class SurveyQuestion(Base):
    __tablename__ = "survey_questions"

    id            = Column(Integer, primary_key=True, index=True)
    key           = Column(String(100), unique=True, index=True, nullable=False)
    question_text = Column(Text, nullable=False)
    question_type = Column(String(50), default="stars") # 'stars', 'text', 'boolean'
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.datetime.utcnow)


class GenerationJobFeedback(Base):
    __tablename__ = "generation_job_feedback"

    id            = Column(Integer, primary_key=True, index=True)
    job_id        = Column(Integer, ForeignKey("generation_jobs.id"), nullable=False)
    question_id   = Column(Integer, ForeignKey("survey_questions.id"), nullable=False)
    
    rating        = Column(Integer, nullable=True) # 1-5 stars
    comment       = Column(Text, nullable=True)     # Optional comments/observations
    created_at    = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (UniqueConstraint('job_id', 'question_id', name='uq_job_question_feedback'),)

    job = relationship("GenerationJob")
    question = relationship("SurveyQuestion")


class TemplateMergeJob(Base):
    """
    Template Merge Engine job tracker.
    Takes an existing PPTX template (category='pptx_template') and a knowledge
    document already ingested, generates content per slide via RAG+LLM, and
    produces a new PPTX that preserves the template's visual structure exactly.
    """
    __tablename__ = "template_merge_jobs"

    id                  = Column(Integer, primary_key=True, index=True)
    brand_id            = Column(Integer, ForeignKey("brands.id"), nullable=True)
    # Nullable: jobs históricos (previos a este fix) no tienen owner conocido —
    # no se hace backfill, gap aceptado (mismo criterio que GenerationJob.owner_id).
    owner_id            = Column(Integer, ForeignKey("users.id"), nullable=True)
    template_asset_id   = Column(Integer, ForeignKey("brand_assets.id"), nullable=False)
    knowledge_filename  = Column(String(512), nullable=False)
    prompt              = Column(Text, nullable=False)

    status              = Column(String(30), default="pending")  # pending|processing|completed|error
    current_step        = Column(Text, nullable=True)
    progress            = Column(Integer, default=0)
    output_path         = Column(String(1024), nullable=True)
    error_detail        = Column(Text, nullable=True)
    # v2: per-slot outcome report ({"slides": [...], "summary": {...}}) built by
    # template_renderer.render_merged_pptx(). NULL on pre-v2 jobs.
    merge_report        = Column(JSON, nullable=True)

    display_name        = Column(String(120), nullable=True)
    created_at          = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    template_asset      = relationship("BrandAsset", foreign_keys=[template_asset_id])


class PromptFavorite(Base):
    """
    Prompt guardado explícitamente por un usuario para reutilizar como punto
    de partida (docs/specs/biblioteca-prompts-favoritos.md). Distinto de
    "reutilizar indicación anterior" (soporte-indicaciones Ayuda 1): ese lee
    GenerationJob.prompt de solo lectura; esto es una copia editable con
    nombre propio, independiente del job de origen.
    """
    __tablename__ = "prompt_favorites"

    id              = Column(Integer, primary_key=True, index=True)
    # Obligatorio: a diferencia de GenerationJob.owner_id, un favorito nace
    # siempre con dueño (no hay filas históricas migradas sin owner).
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=False)
    # Nullable solo para permitir que un superadmin (sin tenant) cree
    # favoritos propios. Asignado del current_user al crear, nunca del body.
    tenant_id       = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    title           = Column(String(120), nullable=False)
    prompt_text     = Column(Text, nullable=False)
    # Mismo shape que GenerationJob.prompt_metadata / interfaz TS PromptMetadata.
    prompt_metadata = Column(JSONB, nullable=True)
    # Sin ondelete a nivel DB (el proyecto no usa ondelete= en ningún FK) —
    # la limpieza es explícita en delete_library_portfolio, mismo patrón que
    # GenerationJobFeedback/ArtDirectorDecision.
    source_job_id   = Column(Integer, ForeignKey("generation_jobs.id"), nullable=True)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class FooterConfig(Base):
    __tablename__ = "footer_configs"

    id              = Column(Integer, primary_key=True, index=True)
    name            = Column(String(100), nullable=False)
    logo_light_path = Column(String(255), nullable=True) # Logo for dark backgrounds
    logo_dark_path  = Column(String(255), nullable=True) # Logo for light backgrounds
    text            = Column(Text, nullable=True)        # Text of the footer
    disclaimer      = Column(String(255), nullable=True) # Disclaimer text (e.g. CONFIDENTIAL FOR {brand} USE ONLY)
    is_active       = Column(Boolean, default=True)
    is_selected     = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)
