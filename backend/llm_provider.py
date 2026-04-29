import os
import json
import time
from typing import List, Optional, Union
try:
    import google.generativeai as genai
except ImportError:
    genai = None  # Gemini not available — use OpenRouter/Mistral/Anthropic instead
import openai
import anthropic
from mistralai import Mistral
from dotenv import load_dotenv

from database import SessionLocal
import models

load_dotenv()

def log_audit(category: str, data: str):
    """Guarda un registro detallado de las decisiones de la IA para auditoría estética."""
    log_path = os.path.join(os.path.dirname(__file__), "llm_audit.log")
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a") as f:
        f.write(f"\n{'='*80}\n")
        f.write(f"[{timestamp}] CATEGORY: {category}\n")
        f.write(f"{data}\n")
        f.write(f"{'='*80}\n")

def get_system_config(key: str, default: str) -> str:
    """Helper para obtener configuración de la DB sin hardcodeo."""
    db = SessionLocal()
    try:
        cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
        return cfg.value if cfg else default
    except:
        return default
    finally:
        db.close()

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
    gem_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
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
        # v23.5: No hardcoded fallbacks here. Fetch from DB.
        model = get_system_config("extraction_synthesis_model", "models/gemini-2.5-flash")
        
    models_to_try = [m.strip() for m in model.split(",")]
    last_error = None
    
    for current_model in models_to_try:
        try:
            print(f"  [LLM] Attempting generation with {current_model}...", flush=True)
            
            # 1. Rutas según el contenido del nombre del modelo
            if "gemini" in current_model.lower():
                # NATIVE GEMINI
                gem_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
                if not gem_key or genai is None: 
                    raise ValueError("Gemini key missing or library not installed")
                genai.configure(api_key=gem_key)
                # Ensure it has 'models/' for the SDK if missing
                m_name = current_model if current_model.startswith("models/") else f"models/{current_model}"
                m = genai.GenerativeModel(m_name)
                response = m.generate_content(prompt, generation_config=genai.GenerationConfig(temperature=0.3, response_mime_type="application/json"))
                # LOG AUDIT (v25.0)
                log_audit(f"GEN_JSON_{current_model}", f"PROMPT:\n{prompt}\n\nRESPONSE:\n{response.text}")
                return json.loads(response.text)
                
            elif "mistral" in current_model.lower() and "/" in current_model:
                # NATIVE MISTRAL (e.g., 'mistral/mistral-large-latest')
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
                
    # FINAL ATTEMPT: Global Fallback from DB
    fallback = get_system_config("global_fallback_model", "models/gemini-2.5-flash")
    if model != fallback:
        print(f"  [LLM] Chain failed. Attempting global emergency fallback ({fallback})...", flush=True)
        try:
            return generate_json(prompt, model=fallback, specialization=specialization)
        except:
            pass
            
    raise last_error or Exception("All models and global fallback failed.")

@retry_with_backoff(retries=2)
def generate_vision_json(prompt: str, image_paths: List[str], model: Optional[str] = None) -> dict:
    """
    UNIVERSAL VISION ENGINE (v18.3).
    Obtiene la cadena de modelos desde system_configs.
    """
    if not model:
        model = get_system_config("extraction_vision_model", "models/gemini-2.5-flash")
        
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
            
            if "gemini" in current_model.lower():
                # ADAPTADOR NATIVO GEMINI
                gem_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
                if not gem_key or genai is None:
                    raise ValueError("Gemini key missing or library not installed")
                genai.configure(api_key=gem_key)
                
                # El adaptador se encarga de la estructura correcta según el SDK
                m_name = current_model if current_model.startswith("models/") else f"models/{current_model}"
                # Pero si falla con models/, el adaptador debe saber reintentar sin él o usar el nombre base
                
                try:
                    m = genai.GenerativeModel(m_name)
                    content = [prompt]
                    for img_data in prepared_imgs:
                        content.append({"mime_type": "image/jpeg", "data": img_data})
                    
                    m = genai.GenerativeModel(m_name)
                    content = [prompt]
                    for img_data in prepared_imgs:
                        content.append({"mime_type": "image/jpeg", "data": img_data})
                    
                    response = m.generate_content(
                        content, 
                        generation_config=genai.GenerationConfig(
                            temperature=0.1, 
                            response_mime_type="application/json"
                        )
                    )
                    # LOG AUDIT (v25.0)
                    log_audit(f"VISION_JSON_{current_model}", f"PROMPT:\n{prompt}\n\nRESPONSE:\n{response.text}")
                    return json.loads(response.text)
                except Exception as gem_err:
                    if "not found" in str(gem_err).lower() and "models/" in m_name:
                        # Reintento inteligente del adaptador: quitar prefijo
                        print(f"  [Vision] Gemini 404 with prefix. Retrying without 'models/'...", flush=True)
                        m = genai.GenerativeModel(m_name.replace("models/", ""))
                        response = m.generate_content(content, generation_config=genai.GenerationConfig(temperature=0.1, response_mime_type="application/json"))
                        return json.loads(response.text)
                    raise gem_err
                
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

    # FINAL ATTEMPT: Global Fallback
    fallback = get_system_config("global_fallback_model", "models/gemini-2.5-flash")
    if model != fallback:
        print(f"  [Vision] Chain failed. Attempting global emergency fallback ({fallback})...", flush=True)
        try:
            return generate_vision_json(prompt, image_paths, model=fallback)
        except:
            pass
            
    raise last_error or Exception("All vision models and global fallback failed.")

def base_64_encode(data):
    import base64
    return base64.b64encode(data).decode('utf-8')

@retry_with_backoff(retries=2)
def get_embeddings_batch(inputs: List[Union[str, bytes]], model: Optional[str] = None) -> List[Optional[list]]:
    """
    UNIVERSAL EMBEDDING ENGINE (v18.6) - Multimodal & Normalized.
    Garantiza salida de 1024 dimensiones para pgvector.
    Soporta Texto (str) e Imágenes (bytes).
    """
    if not inputs: return []
    
    # 1. Determinar modelos a usar
    model_chain = get_system_config("embedding_model_chain", "models/text-embedding-004")
    
    models_to_try = [m.strip() for m in model_chain.split(",")]
    last_error = None
    
    # Target dimension for the DB
    TARGET_DIM = 1024

    def normalize_vector(vec: list, target: int) -> list:
        """Ajusta la dimensión del vector por truncamiento o padding."""
        current = len(vec)
        if current == target: return vec
        if current > target: return vec[:target]
        # Padding con ceros si es menor
        return vec + [0.0] * (target - current)

    for current_model in models_to_try:
        try:
            print(f"  [Embeddings] Attempting with {current_model}...", flush=True)
            
            if "gemini" in current_model.lower() or "embedding" in current_model.lower():
                # NATIVE GOOGLE EMBEDDINGS (Text or Multimodal)
                gem_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
                if not gem_key or genai is None:
                    raise ValueError("Gemini key missing or library not installed")
                genai.configure(api_key=gem_key)
                
                results = []
                for item in inputs:
                    try:
                        # ADAPTADOR INTELIGENTE DE EMBEDDINGS
                        m_name = current_model if current_model.startswith("models/") else f"models/{current_model}"
                        
                        try:
                            if isinstance(item, str):
                                res = genai.embed_content(model=m_name, content=item, task_type="retrieval_document")
                            else:
                                res = genai.embed_content(
                                    model=m_name,
                                    content={'mime_type': 'image/jpeg', 'data': item},
                                    task_type="retrieval_document"
                                )
                            results.append(normalize_vector(res["embedding"], TARGET_DIM))
                        except Exception as gem_err:
                            if "not found" in str(gem_err).lower() and "models/" in m_name:
                                # Reintento sin prefijo
                                alt_name = m_name.replace("models/", "")
                                print(f"  [Embeddings] 404 with prefix. Retrying with: {alt_name}", flush=True)
                                if isinstance(item, str):
                                    res = genai.embed_content(model=alt_name, content=item, task_type="retrieval_document")
                                else:
                                    res = genai.embed_content(
                                        model=alt_name,
                                        content={'mime_type': 'image/jpeg', 'data': item},
                                        task_type="retrieval_document"
                                    )
                                results.append(normalize_vector(res["embedding"], TARGET_DIM))
                            else:
                                print(f"  [Embeddings] Gemini FATAL error (prefix={m_name}): {gem_err}", flush=True)
                                raise gem_err
                    except Exception as e:
                        print(f"  [Embeddings] Item failure in batch: {e}", flush=True)
                        results.append(None)
                
                if any(r is not None for r in results):
                    return results
                else:
                    raise Exception("All items in batch failed for Gemini.")

            elif "mistral" in current_model.lower():
                # MISTRAL EMBEDDINGS (v18.6)
                mis_key = os.getenv("MISTRAL_API_KEY")
                if not mis_key: raise ValueError("No Mistral Key")
                from mistralai import Mistral
                client = Mistral(api_key=mis_key)
                
                # Solo texto para Mistral
                text_inputs = [i for i in inputs if isinstance(i, str)]
                if not text_inputs: continue
                
                res = client.embeddings.create(
                    model="mistral-embed",
                    inputs=text_inputs
                )
                
                # Mapear resultados respetando el orden original y normalizando a 1024
                results = []
                mistral_idx = 0
                for item in inputs:
                    if isinstance(item, str):
                        vec = res.data[mistral_idx].embedding
                        results.append(normalize_vector(vec, TARGET_DIM))
                        mistral_idx += 1
                    else:
                        results.append(None) # Mistral no soporta imágenes
                return results
                if not text_inputs: continue
                response = client.embeddings.create(model="mistral-embed", inputs=text_inputs)
                return [normalize_vector(item.embedding, TARGET_DIM) for item in response.data]

        except Exception as e:
            last_error = e
            print(f"  [Embeddings] {current_model} failed: {e}")
            continue

    raise last_error or Exception("All embedding providers failed.")

def get_embedding(text: str) -> Optional[list]:
    res = get_embeddings_batch([text])
    return res[0] if res else None
