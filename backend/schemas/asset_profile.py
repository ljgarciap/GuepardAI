"""
asset_profile.py — Perfil Visual de Assets (Iteración 1: Mejora de Selección de Imágenes)

Schema Pydantic TOLERANTE para parsear el perfil visual que devuelve el Vision LLM
en la ingesta. Los campos inválidos se descartan individualmente — un perfil
parcial siempre es mejor que ninguno, y un perfil malformado nunca debe abortar
el registro del asset.

Spec: docs/specs/mejora-seleccion-imagenes.md
"""
import re
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

VALID_ORIENTATIONS = {"landscape", "portrait", "square"}
VALID_SUBJECT_POSITIONS = {"left", "center", "right", "full"}
VALID_NEGATIVE_SPACE = {"top", "bottom", "left", "right", "center", "none"}
VALID_LAYOUT_SUITABILITY = {"hero", "split", "accent", "background", "data_grid", "pillars"}

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class AssetComposition(BaseModel):
    subject_position: Optional[str] = None
    negative_space: List[str] = Field(default_factory=list)

    @field_validator("subject_position", mode="before")
    @classmethod
    def _clean_subject_position(cls, v):
        if isinstance(v, str) and v.strip().lower() in VALID_SUBJECT_POSITIONS:
            return v.strip().lower()
        return None

    @field_validator("negative_space", mode="before")
    @classmethod
    def _clean_negative_space(cls, v):
        if not isinstance(v, list):
            return []
        return [z.strip().lower() for z in v
                if isinstance(z, str) and z.strip().lower() in VALID_NEGATIVE_SPACE]


class AssetVisualProfile(BaseModel):
    orientation: Optional[str] = None
    dominant_colors: List[str] = Field(default_factory=list)
    composition: Optional[AssetComposition] = None
    layout_suitability: List[str] = Field(default_factory=list)

    @field_validator("orientation", mode="before")
    @classmethod
    def _clean_orientation(cls, v):
        if isinstance(v, str) and v.strip().lower() in VALID_ORIENTATIONS:
            return v.strip().lower()
        return None

    @field_validator("dominant_colors", mode="before")
    @classmethod
    def _clean_colors(cls, v):
        if not isinstance(v, list):
            return []
        cleaned = []
        for c in v:
            if not isinstance(c, str):
                continue
            c = c.strip().upper()
            if not c.startswith("#"):
                c = f"#{c}"
            if HEX_COLOR_RE.match(c):
                cleaned.append(c)
        return cleaned[:6]

    @field_validator("layout_suitability", mode="before")
    @classmethod
    def _clean_suitability(cls, v):
        if not isinstance(v, list):
            return []
        return [s.strip().lower() for s in v
                if isinstance(s, str) and s.strip().lower() in VALID_LAYOUT_SUITABILITY]

    @classmethod
    def from_llm_response(cls, vision_res: dict) -> Optional["AssetVisualProfile"]:
        """
        Construye el perfil desde la respuesta cruda del Vision LLM.
        Tolerante: campos inválidos quedan en None/vacío. Devuelve None solo si
        la respuesta no contiene ningún campo de perfil aprovechable.
        """
        if not isinstance(vision_res, dict):
            return None

        comp_raw = vision_res.get("composition")
        composition = None
        if isinstance(comp_raw, dict):
            try:
                composition = AssetComposition.model_validate(comp_raw)
            except Exception:
                composition = None

        try:
            profile = cls(
                orientation=vision_res.get("orientation"),
                dominant_colors=vision_res.get("dominant_colors", []),
                composition=composition,
                layout_suitability=vision_res.get("layout_suitability", []),
            )
        except Exception:
            return None

        has_data = bool(
            profile.orientation
            or profile.dominant_colors
            or profile.layout_suitability
            or (profile.composition and (
                profile.composition.subject_position or profile.composition.negative_space
            ))
        )
        return profile if has_data else None

    def to_storage(self) -> dict:
        """Dict listo para persistir en BrandAsset.visual_profile (sin nulls ruidosos)."""
        data = self.model_dump(exclude_none=True)
        if "composition" in data:
            data["composition"] = {k: v for k, v in data["composition"].items() if v}
            if not data["composition"]:
                del data["composition"]
        return {k: v for k, v in data.items() if v}
