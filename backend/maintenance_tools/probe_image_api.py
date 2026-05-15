import os
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
gem_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

print(f"--- STARTING IMAGEN 4.0 PROBE (v8.47) ---")
client = genai.Client(api_key=gem_key)

try:
    print(f"[PROBE] Requesting image from: imagen-4.0-generate-001")
    response = client.models.generate_images(
        model='imagen-4.0-generate-001',
        prompt='A premium executive board room with cinematic lighting, hyper-realistic, 8k resolution, professional architectural photography',
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="16:9"
        )
    )
    
    if response and response.generated_images:
        path = "uploads/probe_imagen4_v8_47.png"
        os.makedirs("uploads", exist_ok=True)
        img_bytes = response.generated_images[0].image.image_bytes
        with open(path, "wb") as f:
            f.write(img_bytes)
        print(f"[SUCCESS] IMAGEN 4.0 SUCCESS! Saved to: {path}")
    else:
        print("[FAILED] No images in response from Imagen 4.0.")
        
except Exception as e:
    print(f"[ERROR] Imagen 4.0 Call failed: {e}")

print("\n--- PROBE FINISHED ---")
