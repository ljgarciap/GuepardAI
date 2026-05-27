import numpy as np
from typing import List, Dict
from providers.llm_provider import get_embedding

# PATRONES SEMÁNTICOS (Vectores de Referencia)
# Estos vectores representan el "ideal" de cada categoría.
CATEGORY_PATTERNS = {
    "person": "A professional person, executive, CEO, human face, portrait, team of people working.",
    "background": "Abstract background, texture, gradient, subtle pattern, corporate wallpaper, empty space.",
    "logo": "Brand logo, graphic mark, typography logo, isolated icon on white or transparent background.",
    "product": "Product photography, physical object, gadget, packaged item, retail product.",
    "infrastructure": "Building, office, warehouse, city skyline, industrial facility.",
}

class AssetIntelligence:
    _cached_patterns = {}

    @classmethod
    def get_pattern_vector(cls, category: str):
        if category not in cls._cached_patterns:
            description = CATEGORY_PATTERNS.get(category)
            if description:
                cls._cached_patterns[category] = get_embedding(description)
        return cls._cached_patterns.get(category)

    @classmethod
    def categorize_by_similarity(cls, asset_vector: List[float]) -> Dict[str, float]:
        """
        Clasifica un asset comparando su vector contra los patrones conocidos.
        Retorna un diccionario de scores (Similitud de Coseno).
        """
        if not asset_vector:
            return {"unclassified": 1.0}

        v1 = np.array(asset_vector)
        scores = {}

        for cat in CATEGORY_PATTERNS.keys():
            v2 = np.array(cls.get_pattern_vector(cat))
            if v2 is not None:
                # Similitud de Coseno
                dot = np.dot(v1, v2)
                norm1 = np.linalg.norm(v1)
                norm2 = np.linalg.norm(v2)
                similarity = dot / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0
                scores[cat] = float(similarity)
        
        # Obtener el ganador
        winner = max(scores, key=scores.get) if scores else "unclassified"
        return {
            "primary_category": winner,
            "confidence": scores.get(winner, 0),
            "all_scores": scores
        }
