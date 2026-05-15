import os
import json
from llm_provider import generate_vision_json

image_path = "/app/uploads/ai_v4_1777894991.png"
prompt = "Analyze this image and provide tags, category (lifestyle_photos or design_elements), and a brief description in JSON format."

print(f"--- STARTING VISION PROBE ---")
print(f"Target Image: {image_path}")

try:
    # Este es el punto donde se colgaba
    result = generate_vision_json(prompt, [image_path], model="models/gemini-2.5-flash")
    print("\n[SUCCESS] Vision Response:")
    print(json.dumps(result, indent=2))
except Exception as e:
    print(f"\n[ERROR] Vision failed: {e}")

print("\n--- PROBE FINISHED ---")
