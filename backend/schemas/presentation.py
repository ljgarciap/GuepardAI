from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ContentManifestSlide(BaseModel):
    slide_number: int
    title: str
    subtitle: Optional[str] = None
    bullets: List[str] = Field(default_factory=list)
    metrics: List[Dict[str, Any]] = Field(default_factory=list)
    metric: Optional[Any] = None
    label: Optional[str] = None
    layout_type: str = "strategic_split"
    section_label: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    planning_json: Dict[str, Any] = Field(default_factory=dict)

class ContentManifest(BaseModel):
    slides: List[ContentManifestSlide]
    job_id: int
    client_name: Optional[str] = None
    # Deck Design Brief (coherencia-artistica-pipeline.md) — None cuando la
    # marca no tiene BrandArtisticEssence o el manifest se construyó por un
    # path que todavía no lo puebla (compatibilidad hacia atrás).
    deck_brief: Optional[Dict[str, Any]] = None

class RenderElement(BaseModel):
    type: str
    role: str
    content: Optional[str] = None
    path: Optional[str] = None
    geometry: Dict[str, float] = Field(default_factory=dict)
    style: Dict[str, Any] = Field(default_factory=dict)

class DesignManifestSlide(BaseModel):
    slide_number: int
    layout_type: str
    primary_asset_path: Optional[str] = None
    background_asset_path: Optional[str] = None
    elements: List[RenderElement] = Field(default_factory=list)

class DesignManifest(BaseModel):
    job_id: int
    slides: List[DesignManifestSlide]
    theme: Dict[str, str] = Field(default_factory=dict)

class PainterAgencyBranding(BaseModel):
    name: str
    # Optional: a brand with no ingested logo asset yet (BrandAsset with
    # category="logos") legitimately has none — both call sites
    # (agents/render_agent.py, services/rendering/layout_engine.py) already
    # compute this as None in that case, and painter.py's apply_branding()
    # already skips drawing the logo when it's falsy. The strict `str` type
    # here was the only thing turning "no logo yet" into a hard pipeline
    # crash instead of a plain "no logo drawn" render.
    logo_path: Optional[str] = None
    client_name: str
    email: str

class PainterSlideData(BaseModel):
    slide_number: int
    layout_type: str
    title: str
    bullets: List[str]
    metric: Optional[Any] = None
    label: Optional[str] = None
    tag: str
    primary_asset_path: Optional[str]
    background_asset_path: Optional[str] = None
    is_last: bool = False
    logo_path: Optional[str] = None
    agency_branding: Optional[PainterAgencyBranding] = None
    metrics: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    elements: List[Dict[str, Any]] = Field(default_factory=list)

class PainterFooterConfig(BaseModel):
    name: str
    logo_light_path: Optional[str] = None
    logo_dark_path: Optional[str] = None
    text: Optional[str] = None
    disclaimer: Optional[str] = None
    is_active: bool = True
    is_selected: bool = False

class RenderManifest(BaseModel):
    slides: List[PainterSlideData]
    logo_path: Optional[str] = None
    logo_light_path: Optional[str] = None
    logo_dark_path: Optional[str] = None
    agency_branding: Optional[PainterAgencyBranding] = None
    is_footer_enabled: bool = True
    footer_config: Optional[PainterFooterConfig] = None
