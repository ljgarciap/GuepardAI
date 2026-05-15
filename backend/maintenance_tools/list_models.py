import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
import models
import google.generativeai as genai

db = SessionLocal()
gem_key = db.query(models.SystemConfig).filter(models.SystemConfig.key == 'gemini_api_key').first().value
genai.configure(api_key=gem_key)

try:
    print("Available Embedding Models:")
    for m in genai.list_models():
        if 'embedContent' in m.supported_generation_methods:
            print(f"- {m.name}")
except Exception as e:
    print("Error:", e)
db.close()
