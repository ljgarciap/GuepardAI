import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from llm_provider import get_system_config
from database import SessionLocal

db = SessionLocal()
mis_key = get_system_config("mistral_api_key", None)
print("Mistral Key from DB:", bool(mis_key))

try:
    from mistralai import Mistral
    print("Mistral library imported")
    client = Mistral(api_key=mis_key)
    print("Mistral client initialized")
    response = client.embeddings.create(
        model="mistral-embed",
        inputs=["Hello World"]
    )
    print("Mistral embedding created! Dim:", len(response.data[0].embedding))
except Exception as e:
    print("Mistral test failed:", e)
db.close()
