import os
import json
import time
from typing import List, Optional
try:
    import google.generativeai as genai
except ImportError:
    genai = None  # Gemini not available — use OpenRouter/Mistral/Anthropic instead
import openai
import anthropic
from mistralai import Mistral
from dotenv import load_dotenv

load_dotenv()

def retry_with_backoff(retries=3, backoff_in_seconds=2):
    def decorator(func):
        def wrapper(*args, **kwargs):
            x = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    err_str = str(e).lower()
                    if "429" in err_str or "quota" in err_str:
                        wait = (30 * (x + 1))
                        print(f"  [Quota] Limit hit. Synchronizing wait: {wait}s...", flush=True)
                        time.sleep(wait)
                        x += 1
                        if x > retries: 
                            raise Exception("Quota Fully Exhausted. Switch providers or check billing.")
                        continue
                        
                    if x == retries:
                        print(f"  [Error] Final abort: {e}", flush=True)
                        raise e
                    else:
                        wait = (backoff_in_seconds * 2 ** x)
                        print(f"  [Retry] Attempt {x+1}/{retries}: {e}", flush=True)
                        time.sleep(wait)
                        x += 1
        return wrapper
    return decorator

def resolve_provider(specialization: str = "general"):
    active = os.getenv("ACTIVE_LLM", "").strip().lower()
    gem_key = os.getenv("GEMINI_API_KEY")
    mis_key = os.getenv("MISTRAL_API_KEY")
    ope_key = os.getenv("OPENAI_API_KEY")
    ant_key = os.getenv("ANTHROPIC_API_KEY")
    
    # SPECIALIZATION ROUTING
    if specialization == "design" and ant_key: 
        print("  [Router] Specialization: DESIGN -> Routing to Anthropic Claude 4.7", flush=True)
        return "anthropic"
    
    # FOR EMBEDDINGS OR GENERAL: Skip anthropic (no embedding support)
    if specialization == "embedding":
        if mis_key: return "mistral"
        if gem_key: return "gemini"
        
    # LOGIC: Favor explicitly active (but skip anthropic for non-design unless forced)
    if active == "mistral" and mis_key: return "mistral"
    if active == "gemini" and gem_key: return "gemini"
    
    if mis_key: return "mistral" 
    if gem_key: return "gemini"
    if ant_key and specialization == "design": return "anthropic"
    if ope_key: return "openai"
    
    raise ValueError("API_KEY missing for required provider.")

@retry_with_backoff(retries=3)
def generate_json(prompt: str, specialization: str = "general") -> dict:
    primary_provider = resolve_provider(specialization)
    providers_to_try = [primary_provider, "openrouter", "gemini", "mistral"]
    if os.getenv("OPENROUTER_API_KEY"):
        # Prioritize OpenRouter for design if we have the key
        providers_to_try = ["openrouter"] + [p for p in providers_to_try if p != "openrouter"]
    
    # De-duplicate while preserving order
    providers_to_try = list(dict.fromkeys(providers_to_try))
    
    last_error = None
    for provider in providers_to_try:
        try:
            print(f"  [LLM] Attempting generation with {provider.upper()}...", flush=True)
            if provider == "openrouter":
                or_key = os.getenv("OPENROUTER_API_KEY")
                if not or_key: raise ValueError("No OpenRouter Key")
                client = openai.OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=or_key,
                )
                # Corrected slug for OpenRouter (Updated to Claude 3.7 Sonnet for 2026)
                response = client.chat.completions.create(
                    model="anthropic/claude-3.7-sonnet",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                return json.loads(response.choices[0].message.content)

            elif provider == "anthropic":
                ant_key = os.getenv("ANTHROPIC_API_KEY")
                if not ant_key: raise ValueError("No Anthropic Key")
                client = anthropic.Anthropic(api_key=ant_key)
                response = client.messages.create(
                    model="claude-opus-4-7",
                    max_tokens=6144,
                    system="You are an expert Strategic Architect. Return STRICT JSON ONLY.",
                    messages=[{"role": "user", "content": prompt}]
                )
                text = response.content[0].text
                if "```json" in text: text = text.split("```json")[1].split("```")[0]
                elif "```" in text: text = text.split("```")[1].split("```")[0]
                return json.loads(text.strip())
                
            elif provider == "gemini":
                gem_key = os.getenv("GEMINI_API_KEY")
                if not gem_key: raise ValueError("No Gemini Key")
                genai.configure(api_key=gem_key)
                # Updated to Gemini 2.5 Flash for 2026
                model = genai.GenerativeModel("models/gemini-2.5-flash")
                response = model.generate_content(prompt, generation_config=genai.GenerationConfig(temperature=0.3, response_mime_type="application/json"))
                return json.loads(response.text)
                
            elif provider == "mistral":
                mis_key = os.getenv("MISTRAL_API_KEY")
                if not mis_key: raise ValueError("No Mistral Key")
                client = Mistral(api_key=mis_key)
                response = client.chat.complete(model="mistral-large-latest", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
                return json.loads(response.choices[0].message.content)

        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            if "quota" in err_msg or "credit" in err_msg or "429" in err_msg:
                print(f"  [LLM] {provider.upper()} exhausted/limit hit. Falling back to next provider...", flush=True)
                continue
            else:
                # If it's a structural error (invalid JSON), maybe retry same provider or re-raise
                print(f"  [LLM] Error with {provider.upper()}: {e}")
                continue
                
    raise last_error or Exception("All providers failed.")

@retry_with_backoff(retries=2)
def generate_vision_json(prompt: str, image_paths: List[str]) -> dict:
    """
    ULTRA-POWERFUL VISION SYNTHESIS.
    Analyzes images + text to extract high-level design intelligence.
    Uses OpenRouter (Claude 3.5 Sonnet) or Gemini 1.5 Flash.
    """
    # 1. Prepare Base64 images for OpenRouter/OpenAI style (with resizing)
    from PIL import Image
    import io
    import base64

    def prepare_image(path, max_size=(1024, 1024)):
        with Image.open(path) as img:
            img.thumbnail(max_size)
            # Convert to RGB if necessary (Alpha channel can sometimes cause issues)
            if img.mode in ("RGBA", "P"): img = img.convert("RGB")
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            return buffered.getvalue()

    or_key = os.getenv("OPENROUTER_API_KEY")
    if or_key:
        try:
            print(f"  [Vision] Analyzing {len(image_paths)} assets via OPENROUTER (Claude 3.7 Sonnet)...", flush=True)
            client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=or_key)
            
            content = [{"type": "text", "text": prompt}]
            for img_path in image_paths:
                if os.path.exists(img_path):
                    img_data = prepare_image(img_path)
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base_64_encode(img_data)}"}
                    })
            
            response = client.chat.completions.create(
                model="anthropic/claude-3.7-sonnet",
                messages=[{"role": "user", "content": content}],
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"  [Vision] OpenRouter failed: {e}. Falling back to Gemini...")

    # 2. Fallback to Gemini 1.5 Flash (Native)
    gem_key = os.getenv("GEMINI_API_KEY")
    if gem_key:
        try:
            print(f"  [Vision] Analyzing via NATIVE GEMINI 2.5 FLASH...", flush=True)
            genai.configure(api_key=gem_key)
            model = genai.GenerativeModel("models/gemini-2.5-flash")
            content = [prompt]
            for p in image_paths:
                if os.path.exists(p):
                    # Prepare bytes directly
                    with Image.open(p) as img:
                        img.thumbnail((1024, 1024))
                        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                        buffered = io.BytesIO()
                        img.save(buffered, format="JPEG", quality=85)
                        content.append({
                            "mime_type": "image/jpeg",
                            "data": buffered.getvalue()
                        })
            
            response = model.generate_content(content, generation_config=genai.GenerationConfig(response_mime_type="application/json"))
            return json.loads(response.text)
        except Exception as e:
            print(f"  [Vision] Gemini Vision failed: {e}")

    raise Exception("All Vision providers failed.")

def base_64_encode(data):
    import base64
    return base64.b64encode(data).decode('utf-8')

@retry_with_backoff(retries=3)
def get_embeddings_batch(texts: List[str]) -> List[Optional[list]]:
    """
    ULTRA-EFFICIENT BATCH EMBEDDING (Auto-Provider Detection).
    Defaults to MISTRAL (1024-dim) for best RAG performance without quotas.
    """
    if not texts: return []
    provider = resolve_provider(specialization="embedding")
    
    if provider == "mistral":
        client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))
        # Mistral-embed: 1024 dimensions. Reliable and high quality.
        response = client.embeddings.create(model="mistral-embed", inputs=texts)
        return [item.embedding for item in response.data]
        
    elif provider == "gemini":
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        # Warning: This returns 768-dim, but our DB is now 1024-dim for Mistral.
        # This will only be a fallback if Mistral key is missing.
        response = genai.embed_content(model="models/gemini-embedding-001", content=texts, task_type="retrieval_document")
        return response.get("embedding", [])
        
    elif provider == "openai":
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=30)
        response = client.embeddings.create(input=texts, model="text-embedding-3-small")
        return [item.embedding for item in response.data]

def get_embedding(text: str) -> Optional[list]:
    res = get_embeddings_batch([text])
    return res[0] if res else None
