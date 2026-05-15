import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
or_key = os.getenv("OPENROUTER_API_KEY")

print(f"--- STARTING GPT-5.4 IMAGE PROBE (v8.61) ---")

url = "https://openrouter.ai/api/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {or_key}",
    "Content-Type": "application/json"
}

payload = {
    "model": "openai/gpt-5.4-image-2",
    "modalities": ["image"],
    "messages": [
        {
            "role": "user",
            "content": "A high-quality professional lifestyle photo of a modern executive office, morning sunlight, cinematic depth of field, 8k resolution"
        }
    ]
}

try:
    print(f"[PROBE] Requesting image from GPT-5.4 via OpenRouter...")
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    res_json = response.json()
    
    if "choices" in res_json:
        print(f"[SUCCESS] Response received!")
        with open("uploads/gpt5_probe_response.json", "w") as f:
            json.dump(res_json, f, indent=2)
        print(f"[DEBUG] Check uploads/gpt5_probe_response.json for details")
    else:
        print(f"[FAILED] Error: {res_json}")

except Exception as e:
    print(f"[ERROR] GPT-5.4 Probe failed: {e}")

print("\n--- PROBE FINISHED ---")
