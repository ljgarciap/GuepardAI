import os
import json
import base64
import logging
import requests

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://vision:11434")

def generate_autonomous_layout(image_path: str, title: str, grammar_type: str, design_system: dict) -> dict:
    """
    Acts as the sole Autonomous Art Director.
    Analyzes the image and returns the final JSON geometry for the layout.
    """
    if not image_path: return None
    
    # Resolving absolute path
    filename = os.path.basename(image_path)
    candidates = [
        image_path if os.path.isabs(image_path) else None,
        os.path.abspath(os.path.join("uploads", filename)),
        os.path.abspath(os.path.join("backend", "uploads", filename))
    ]
    resolved_path = next((p for p in candidates if p and os.path.exists(p)), None)
    
    if not resolved_path:
        logger.warning(f"[AutonomousVLM] Image not found: {image_path}")
        return None

    try:
        with open(resolved_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"[AutonomousVLM] Failed to read image: {e}")
        return None

    prompt = f"""
    You are an expert autonomous Art Director and UX Designer.
    Analyze the uploaded background image and the slide requirements.
    
    Slide Title: "{title}"
    Composition Type: "{grammar_type}"
    Design System Colors: {json.dumps(design_system.get('colors', {}))}
    
    Your task: Look at the image and decide the BEST organic placement for the text panels.
    - Find the "negative space" (empty areas without faces or important subjects).
    - Design a beautiful Glassmorphism layout (panels) that fit inside that negative space.
    - You can use floating banners, overlapping cards, lower thirds, or sidebars.
    - DO NOT cover important parts of the image!
    
    Return ONLY a JSON object with this exact structure:
    {{
      "glass_panels": [
        {{
          "x_pct": <float 0-100>,
          "y_pct": <float 0-100>,
          "w_pct": <float 0-100>,
          "h_pct": <float 0-100>,
          "color_hex": "<hex string, e.g., #FFFFFF or the design system primary color>",
          "transparency": <float 0.0-1.0>,
          "rounded": <boolean>,
          "shadow": <boolean>
        }}
      ],
      "image_treatment": {{
        "style": "full_bleed"
      }}
    }}
    
    Do not return any other text, markdown formatting, or explanation. Just the raw JSON.
    """

    payload = {
        "model": "qwen2.5vl",
        "prompt": prompt,
        "images": [encoded_string],
        "stream": False,
        "format": "json"
    }

    try:
        logger.info(f"  [AutonomousVLM] Analyzing {os.path.basename(image_path)}...")
        response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()
        result_text = data.get("response", "{}")
        
        parsed = json.loads(result_text)
        return parsed
    except Exception as e:
        logger.error(f"[AutonomousVLM] Failed to generate layout for {os.path.basename(image_path)}: {e}")
        return None
