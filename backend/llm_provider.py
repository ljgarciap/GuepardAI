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
        if os.getenv("OPENROUTER_API_KEY"): return "openrouter"
        if mis_key: return "mistral"
        if gem_key: return "gemini"
        if ope_key: return "openai"
        
    # LOGIC: Favor explicitly active (but skip anthropic for non-design unless forced)
    if active == "mistral" and mis_key: return "mistral"
    if active == "gemini" and gem_key: return "gemini"
    
    if mis_key: return "mistral" 
    if gem_key: return "gemini"
    if ant_key and specialization == "design": return "anthropic"
    if ope_key: return "openai"
    
    raise ValueError("API_KEY missing for required provider.")

@retry_with_backoff(retries=3)
def generate_json(prompt: str, model: Optional[str] = None, specialization: str = "general") -> dict:
    """
    UNIVERSAL AI ENGINE (v18.2) - Parametric Failover.
    Soporta cadenas de modelos: 'models/gemini-1.5-flash,mistral/mistral-large-latest'
    """
    if not model:
        # Fallback si no se especifica modelo
        model = "models/gemini-1.5-flash,mistral/mistral-large-latest"
        
    models_to_try = [m.strip() for m in model.split(",")]
    last_error = None
    
    for current_model in models_to_try:
        try:
            print(f"  [LLM] Attempting generation with {current_model}...", flush=True)
            
            # 1. Rutas según el prefijo del modelo
            if current_model.startswith("models/"):
                # NATIVE GEMINI
                gem_key = os.getenv("GEMINI_API_KEY")
                if not gem_key: raise ValueError("No Gemini Key")
                genai.configure(api_key=gem_key)
                m = genai.GenerativeModel(current_model)
                response = m.generate_content(prompt, generation_config=genai.GenerationConfig(temperature=0.3, response_mime_type="application/json"))
                return json.loads(response.text)
                
            elif current_model.startswith("mistral/"):
                # NATIVE MISTRAL
                mis_key = os.getenv("MISTRAL_API_KEY")
                if not mis_key: raise ValueError("No Mistral Key")
                client = Mistral(api_key=mis_key)
                # Mistral slugs don't usually have the prefix, but we remove it for the API call
                m_slug = current_model.replace("mistral/", "")
                response = client.chat.complete(model=m_slug, messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
                return json.loads(response.choices[0].message.content)
            
            else:
                # OPENROUTER (Default fallback for other slugs like 'anthropic/claude-3.7-sonnet')
                or_key = os.getenv("OPENROUTER_API_KEY")
                if not or_key: raise ValueError("No OpenRouter Key")
                client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=or_key)
                response = client.chat.completions.create(
                    model=current_model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                return json.loads(response.choices[0].message.content)

        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            if "quota" in err_msg or "credit" in err_msg or "429" in err_msg or "limit" in err_msg:
                print(f"  [LLM] Model {current_model} exhausted/limit hit. Falling back...", flush=True)
                continue
            else:
                print(f"  [LLM] Error with {current_model}: {e}")
                continue
                
    raise last_error or Exception("All models in chain failed.")

@retry_with_backoff(retries=2)
def generate_vision_json(prompt: str, image_paths: List[str], model: Optional[str] = None) -> dict:
    """
    UNIVERSAL VISION ENGINE (v18.2).
    Soporta cadenas: 'anthropic/claude-3.7-sonnet,models/gemini-1.5-flash'
    """
    if not model:
        model = "anthropic/claude-3.7-sonnet,models/gemini-1.5-flash"
        
    models_to_try = [m.strip() for m in model.split(",")]
    
    # Pre-procesar imágenes una sola vez
    from PIL import Image
    import io

    def prepare_image(path, max_size=(1024, 1024)):
        with Image.open(path) as img:
            img.thumbnail(max_size)
            if img.mode in ("RGBA", "P"): img = img.convert("RGB")
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            return buffered.getvalue()

    prepared_imgs = []
    for p in image_paths:
        if os.path.exists(p): prepared_imgs.append(prepare_image(p))

    last_error = None
    for current_model in models_to_try:
        try:
            print(f"  [Vision] Attempting with {current_model}...", flush=True)
            
            if current_model.startswith("models/"):
                # NATIVE GEMINI VISION
                gem_key = os.getenv("GEMINI_API_KEY")
                if not gem_key: raise ValueError("No Gemini Key")
                genai.configure(api_key=gem_key)
                m = genai.GenerativeModel(current_model)
                content = [prompt]
                for img_data in prepared_imgs:
                    content.append({"mime_type": "image/jpeg", "data": img_data})
                
                response = m.generate_content(content, generation_config=genai.GenerationConfig(temperature=0.2, response_mime_type="application/json"))
                return json.loads(response.text)
                
            else:
                # OPENROUTER VISION (Claude 3.7 / GPT-4o)
                or_key = os.getenv("OPENROUTER_API_KEY")
                if not or_key: raise ValueError("No OpenRouter Key")
                client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=or_key)
                
                msg_content = [{"type": "text", "text": prompt}]
                for img_data in prepared_imgs:
                    msg_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base_64_encode(img_data)}"}
                    })
                
                response = client.chat.completions.create(
                    model=current_model,
                    messages=[{"role": "user", "content": msg_content}],
                    max_tokens=1000,
                    response_format={"type": "json_object"}
                )
                return json.loads(response.choices[0].message.content)

        except Exception as e:
            last_error = e
            print(f"  [Vision] {current_model} failed: {e}. Trying next...")
            continue

    raise last_error or Exception("All vision models failed.")

def base_64_encode(data):
    import base64
    return base64.b64encode(data).decode('utf-8')

@retry_with_backoff(retries=2)
def get_embeddings_batch(texts: List[str]) -> List[Optional[list]]:
    """
    ULTRA-EFFICIENT BATCH EMBEDDING (With Redundant Fallback Chain).
    """
    if not texts: return []
    
    # Intentamos primero con el proveedor preferido (OpenRouter -> Mistral -> Gemini)
    providers_to_try = []
    if os.getenv("OPENROUTER_API_KEY"): providers_to_try.append("openrouter")
    if os.getenv("MISTRAL_API_KEY"): providers_to_try.append("mistral")
    if os.getenv("GEMINI_API_KEY"): providers_to_try.append("gemini")
    
    last_error = None
    for provider in providers_to_try:
        try:
            print(f"  [Embeddings] Attempting with {provider.upper()}...", flush=True)
            if provider == "openrouter":
                client = openai.OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=os.getenv("OPENROUTER_API_KEY"),
                )
                response = client.embeddings.create(input=texts, model="mistralai/mistral-embed")
                return [item.embedding for item in response.data]

            elif provider == "gemini":
                genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                # Note: Gemini uses 768-dim, we might need to pad/truncate if DB is 1024
                response = genai.embed_content(model="models/text-embedding-004", content=texts, task_type="retrieval_document")
                embeddings = response.get("embedding", [])
                # Handle 768 to 1024 padding if needed
                return embeddings

            elif provider == "mistral":
                client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))
                response = client.embeddings.create(model="mistral-embed", inputs=texts)
                return [item.embedding for item in response.data]
        except Exception as e:
            print(f"  [Embeddings] Provider {provider} failed: {e}")
            last_error = e
            continue
            
    if last_error: raise last_error
    return []

def get_embedding(text: str) -> Optional[list]:
    res = get_embeddings_batch([text])
    return res[0] if res else None
