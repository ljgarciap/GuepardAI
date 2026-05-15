import os
import json
import google.generativeai as genai
from mistralai import Mistral
import openai
from dotenv import load_dotenv

load_dotenv()

def test_gemini_vision(model_name):
    print(f"\n--- Testing GEMINI VISION: {model_name} ---")
    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel(model_name)
        # Test simple text request to check model availability
        response = model.generate_content("Hello, respond with 'OK'")
        print(f"  [SUCCESS] {model_name} responded: {response.text}")
        return True
    except Exception as e:
        print(f"  [FAILED] {model_name} error: {e}")
        return False

def test_gemini_embedding(model_name):
    print(f"\n--- Testing GEMINI EMBEDDING: {model_name} ---")
    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        res = genai.embed_content(model=model_name, content="Hello World", task_type="retrieval_document")
        print(f"  [SUCCESS] {model_name} dimension: {len(res['embedding'])}")
        return True
    except Exception as e:
        print(f"  [FAILED] {model_name} error: {e}")
        return False

def test_mistral_embedding():
    print("\n--- Testing MISTRAL EMBEDDING ---")
    try:
        client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))
        res = client.embeddings.create(model="mistral-embed", inputs=["Hello World"])
        print(f"  [SUCCESS] Mistral dimension: {len(res.data[0].embedding)}")
        return True
    except Exception as e:
        print(f"  [FAILED] Mistral error: {e}")
        return False

def test_openrouter_claude():
    print("\n--- Testing OPENROUTER (Claude 3.7) ---")
    try:
        client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.getenv("OPENROUTER_API_KEY"))
        response = client.chat.completions.create(
            model="anthropic/claude-3.7-sonnet",
            messages=[{"role": "user", "content": "Respond OK"}]
        )
        print(f"  [SUCCESS] Claude responded: {response.choices[0].message.content}")
        return True
    except Exception as e:
        print(f"  [FAILED] Claude error: {e}")
        return False

def list_available_models():
    print("\n--- Listing Available GEMINI Models ---")
    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        for m in genai.list_models():
            print(f"  - {m.name} (supports: {m.supported_generation_methods})")
        return True
    except Exception as e:
        print(f"  [FAILED] Listing models error: {e}")
        return False

if __name__ == "__main__":
    print("=== POWERAI API AUDIT START ===\n")
    
    # Test the verified models from the list
    test_gemini_vision("models/gemini-2.5-flash")
    test_gemini_embedding("models/gemini-embedding-2")
    
    # Test Mistral
    test_mistral_embedding()
    
    # Test OpenRouter
    test_openrouter_claude()
    
    print("\n=== AUDIT COMPLETE ===")
