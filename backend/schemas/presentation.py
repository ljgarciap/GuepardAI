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
    logo_path: str
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

class RenderManifest(BaseModel):
    slides: List[PainterSlideData]
    logo_path: Optional[str] = None
    agency_branding: Optional[PainterAgencyBranding] = None
