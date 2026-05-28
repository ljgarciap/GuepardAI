import os
import json
from loguru import logger
from providers.llm_provider import generate_vision_json

def evaluate_image_with_vision(image_path: str, context_text: str) -> float:
    """
    Usa el modelo de visión principal (Pixtral/Gemini) para evaluar qué tan bien encaja
    la imagen real con el texto corporativo de la diapositiva.
    Retorna un score (0.0 a 1.0).
    """
    prompt = (
        f"You are a strict corporate Art Director. Analyze the provided image against this context: '{context_text}'. "
        "Return a JSON object with exactly one key 'score' containing a float between 0.0 and 1.0. "
        "A high score (0.8-1.0) means the image perfectly represents the context in a professional, corporate setting. "
        "A low score (0.0-0.4) means the image is irrelevant, childish, or inappropriate for the context (like children playing cards instead of corporate loyalty cards). "
        "Return ONLY the JSON object, nothing else."
    )

    try:
        data = generate_vision_json(prompt, [image_path])
        score = float(data.get("score", 0.0))
        return min(max(score, 0.0), 1.0)
    except Exception as e:
        logger.error(f"[Vision] Evaluation failed for {os.path.basename(image_path)}: {e}")
        # Fallback to a neutral score so we don't block the pipeline if vision is down
        return 0.5
