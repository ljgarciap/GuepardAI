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
    print("Testing text-embedding-004 without output_dimensionality...")
    res = genai.embed_content(
        model="models/text-embedding-004", 
        content="Hello world", 
        task_type="retrieval_document"
    )
    print("Success! Dimensions:", len(res['embedding']))
except Exception as e:
    print("Error:", e)

try:
    print("Testing text-embedding-004 WITH output_dimensionality...")
    res = genai.embed_content(
        model="models/text-embedding-004", 
        content="Hello world", 
        task_type="retrieval_document",
        output_dimensionality=1024
    )
    print("Success! Dimensions:", len(res['embedding']))
except Exception as e:
    print("Error:", e)
db.close()
