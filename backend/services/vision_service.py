import requests
import base64
import os
import json
from loguru import logger

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://vision:11434")

def encode_image_base64(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def evaluate_image_with_vision(image_path: str, context_text: str) -> float:
    """
    Usa el modelo de visión local (moondream) para evaluar qué tan bien encaja
    la imagen real con el texto corporativo de la diapositiva.
    Retorna un score (0.0 a 1.0).
    """
    try:
        b64_image = encode_image_base64(image_path)
    except Exception as e:
        logger.error(f"[Vision] Could not load image {image_path}: {e}")
        return 0.0

    prompt = (
        f"You are a strict corporate Art Director. Analyze the provided image against this context: '{context_text}'. "
        "Return a JSON object with exactly one key 'score' containing a float between 0.0 and 1.0. "
        "A high score (0.8-1.0) means the image perfectly represents the context in a professional, corporate setting. "
        "A low score (0.0-0.4) means the image is irrelevant, childish, or inappropriate for the context (like children playing cards instead of corporate loyalty cards). "
        "Return ONLY the JSON object, nothing else."
    )

    payload = {
        "model": "minicpm-v",
        "prompt": prompt,
        "images": [b64_image],
        "stream": False,
        "format": "json"
    }

    try:
        response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        result_text = data.get("response", "{}")
        
        parsed = json.loads(result_text)
        score = float(parsed.get("score", 0.0))
        return min(max(score, 0.0), 1.0)
    except Exception as e:
        logger.error(f"[Vision] Ollama evaluation failed for {os.path.basename(image_path)}: {e}")
        # Fallback to a neutral score so we don't block the pipeline if vision is down
        return 0.5
