import os
import json
import time
import re
from typing import List, Optional, Union
try:
    import google.generativeai as genai
except ImportError:
    genai = None  # Gemini not available — use OpenRouter/Mistral/Anthropic instead
import openai
import anthropic
from mistralai import Mistral
from dotenv import load_dotenv
try:
    from google import genai as google_genai
    from google.genai import types as genai_types
except ImportError:
    google_genai = None

from database import SessionLocal
import models
import threading

local_vlm_lock = threading.Lock()
load_dotenv()

def clean_json_string(s: str) -> str:
    """
    Elimina caracteres de control no permitidos en JSON y limpia markdown blocks.
    """
    if not s: return "{}"
    # Quitar bloques de markdown ```json ... ```
    s = re.sub(r'```json\s*', '', s)
    s = re.sub(r'```\s*', '', s)
    
    # Eliminar caracteres de control (0-31) excepto \n, \r, \t si es necesario
    # Pero lo más común que rompe es \n literal dentro de comillas
    # Esta es una versión simplificada pero efectiva
    return s.strip()

def log_audit(category: str, data: str):
    """Saves a detailed record de las AI decisions para aesthetic audit."""
    log_path = os.path.join(os.path.dirname(__file__), "llm_audit.log")
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a") as f:
        f.write(f"\n{'='*80}\n")
        f.write(f"[{timestamp}] CATEGORY: {category}\n")
        f.write(f"{data}\n")
        f.write(f"{'='*80}\n")

def get_system_config(key: str, default: str) -> str:
    """Helper to get DB config without hardcoding. Prioritizes ENV variables (UPPERCASE)."""
    # 1. Prioritize ENV
    env_val = os.getenv(key.upper())
    if env_val: return env_val

    # 2. Database
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
                    if "exceeded its monthly spending cap" in err_str:
                        print(f"  [Error] Hard billing limit hit. Aborting retries for: {e}", flush=True)
                        raise e
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
    Soporta cadenas de modelos: 'gemini-flash-latest,mistral/mistral-large-latest'
    """
    if not model:
        # v23.5: No hardcoded fallbacks here. Fetch from DB.
        model = get_system_config("extraction_synthesis_model", "gemini-flash-latest")
        
    models_to_try = [m.strip() for m in model.split(",")]
    last_error = None
    
    for current_model in models_to_try:
        try:
            # v23.6: Auto-strip 'models/' prefix if present (SDK handles this internally)
            api_model_name = current_model
            if "gemini" in api_model_name.lower() and api_model_name.startswith("models/"):
                api_model_name = api_model_name.replace("models/", "")

            print(f"  [LLM] Attempting generation with {api_model_name}...", flush=True)
            
            # 1. Routes according to model name content
            if "gemini" in current_model.lower():
                # NATIVE GEMINI
                gem_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
                if not gem_key or genai is None: 
                    raise ValueError("Gemini key missing or library not installed")
                genai.configure(api_key=gem_key)
                # v23.7: Use cleaned model name (stripping 'models/') to avoid 404s
                m = genai.GenerativeModel(api_model_name)
                # v8.54: Added mandatory timeout to prevent hangs
                response = m.generate_content(
                    prompt, 
                    generation_config=genai.GenerationConfig(temperature=0.3, response_mime_type="application/json"),
                    request_options={"timeout": 60} 
                )
                # LOG AUDIT (v25.0)
                log_audit(f"GEN_JSON_{current_model}", f"PROMPT:\n{prompt}\n\nRESPONSE:\n{response.text}")
                
                # v25.1: Aggressive JSON cleaning
                clean_text = clean_json_string(response.text)
                return json.loads(clean_text)
                
            elif "mistral" in current_model.lower() and "/" in current_model:
                # NATIVE MISTRAL (e.g., 'mistral/mistral-large-latest')
                # NATIVE MISTRAL
                mis_key = os.getenv("MISTRAL_API_KEY")
                if not mis_key: raise ValueError("No Mistral Key")
                client = Mistral(api_key=mis_key)
                # Mistral slugs don't usually have the prefix, but we remove it for the API call
                m_slug = current_model.replace("mistral/", "")
                response = client.chat.complete(model=m_slug, messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
                if not response or not getattr(response, "choices", None) or len(response.choices) == 0:
                    raise ValueError(f"Mistral model {current_model} returned no choices.")
                
                content = response.choices[0].message.content
                log_audit(f"GEN_JSON_{current_model}", f"PROMPT:\n{prompt}\n\nRESPONSE:\n{content}")
                
                clean_text = clean_json_string(content)
                return json.loads(clean_text)
            
            elif "qwen" in current_model.lower() or "ollama" in current_model.lower():
                # LOCAL OLLAMA FALLBACK
                import requests
                ollama_url = os.getenv("OLLAMA_URL", "http://vision:11434")
                with local_vlm_lock:
                    clean_model = current_model.replace("ollama/", "")
                    payload = {"model": clean_model, "prompt": prompt, "stream": False, "format": "json"}
                    response = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=300)
                    response.raise_for_status()
                    content = response.json().get("response", "{}")
                    log_audit(f"GEN_JSON_{current_model}", f"PROMPT:\n{prompt}\n\nRESPONSE:\n{content}")
                    return json.loads(clean_json_string(content))
            
            else:
                # OPENROUTER (Default fallback for other slugs like 'anthropic/claude-3.5-sonnet')
                or_key = os.getenv("OPENROUTER_API_KEY")
                if not or_key: raise ValueError("No OpenRouter Key")
                client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=or_key)
                response = client.chat.completions.create(
                    model=current_model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                if not response or not getattr(response, "choices", None) or len(response.choices) == 0:
                    raise ValueError(f"OpenRouter model {current_model} returned no choices.")
                
                content = response.choices[0].message.content
                log_audit(f"GEN_JSON_{current_model}", f"PROMPT:\n{prompt}\n\nRESPONSE:\n{content}")
                
                clean_text = clean_json_string(content)
                return json.loads(clean_text)

        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            if "429" in err_msg or "too many requests" in err_msg:
                # Simple inline retry for rate limits (Mistral Experiment tier is 1 RPS)
                success = False
                for attempt in range(3):
                    print(f"  [LLM] Rate limit 429 on {current_model}. Wait 2s and retry (Attempt {attempt+1}/3)...", flush=True)
                    time.sleep(2)
                    try:
                        if "gemini" in api_model_name.lower():
                            if "flash" in api_model_name:
                                res = genai.GenerativeModel(api_model_name).generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                            else:
                                res = genai.GenerativeModel(api_model_name).generate_content(prompt)
                            content = res.text
                        elif "mistral" in current_model.lower():
                            m_slug = current_model.replace("mistral/", "")
                            res = client.chat.complete(model=m_slug, messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
                            content = res.choices[0].message.content
                        elif "qwen" in current_model.lower() or "ollama" in current_model.lower():
                            res = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=300)
                            content = res.json().get("response", "{}")
                        else:
                            res = client.chat.completions.create(model=current_model, messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
                            content = res.choices[0].message.content
                        
                        log_audit(f"GEN_JSON_{current_model}_RETRY", f"PROMPT:\n{prompt}\n\nRESPONSE:\n{content}")
                        clean_text = clean_json_string(content)
                        return json.loads(clean_text)
                    except Exception as retry_e:
                        last_error = retry_e
                
                print(f"  [LLM] Model {current_model} rate limit persists after 3 retries. Falling back...", flush=True)
                continue
            elif "quota" in err_msg or "credit" in err_msg or "limit" in err_msg:
                print(f"  [LLM] Model {current_model} exhausted/limit hit. Falling back...", flush=True)
                continue
            else:
                print(f"  [LLM] Error with {current_model}: {e}")
                continue
                
    # FINAL ATTEMPT: Global Fallback from DB
    fallback = get_system_config("global_fallback_model", "gemini-flash-latest")
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
        model = get_system_config("extraction_vision_model", "gemini-flash-latest")
        
    models_to_try = [m.strip() for m in model.split(",")]
    
    # Pre-process images once
    from PIL import Image
    import io

    def prepare_image(path, max_size=(1024, 1024)):
        with Image.open(path) as img:
            img.thumbnail(max_size)
            # v13.0: High-Contrast Background for Transparent Assets (Designer Rigor)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGBA")
                # Create a neutral gray background to ensure visibility of both white and black elements
                bg = Image.new("RGBA", img.size, (128, 128, 128, 255))
                bg.paste(img, (0, 0), img)
                img = bg.convert("RGB")
            else:
                img = img.convert("RGB")
            
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
                gem_key = get_system_config("gemini_api_key", None) or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
                if not gem_key or genai is None:
                    raise ValueError("Gemini key missing or library not installed")
                genai.configure(api_key=gem_key)
                
                # The adapter handles the correct structure according to the SDK
                m_name = current_model.replace("models/", "") if "gemini" in current_model.lower() else current_model
                # But if it fails with models/, the adapter must know how to retry without it or use the base name
                
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
                        ),
                        request_options={"timeout": 60} # v8.54: Vision Timeout
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
                
            elif "mistral" in current_model.lower() or "pixtral" in current_model.lower():
                # NATIVE MISTRAL VISION (Pixtral 12B / Large)
                mis_key = get_system_config("mistral_api_key", None) or os.getenv("MISTRAL_API_KEY")
                if not mis_key: raise ValueError("No Mistral Key for Pixtral")
                
                # Slug fix
                m_slug = current_model.replace("mistral/", "")
                if "pixtral" not in m_slug:
                    m_slug = "pixtral-12b-2409" # Default fallback
                    
                client = Mistral(api_key=mis_key)
                msg_content = [{"type": "text", "text": prompt}]
                for img_data in prepared_imgs:
                    msg_content.append({
                        "type": "image_url",
                        "image_url": f"data:image/jpeg;base64,{base_64_encode(img_data)}"
                    })
                
                response = client.chat.complete(
                    model=m_slug,
                    messages=[{"role": "user", "content": msg_content}],
                    response_format={"type": "json_object"}
                )
                
                content_text = response.choices[0].message.content
                log_audit(f"VISION_JSON_{current_model}", f"PROMPT:\n{prompt}\n\nRESPONSE:\n{content_text}")
                return json.loads(clean_json_string(content_text))
                
            elif "qwen" in current_model.lower() or "ollama" in current_model.lower():
                # LOCAL OLLAMA VISION FALLBACK
                import requests
                ollama_url = os.getenv("OLLAMA_URL", "http://vision:11434")
                with local_vlm_lock:
                    b64_images = [base_64_encode(img_data) for img_data in prepared_imgs]
                    clean_model = current_model.replace("ollama/", "")
                    payload = {"model": clean_model, "prompt": prompt, "images": b64_images, "stream": False, "format": "json"}
                    response = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=300)
                    response.raise_for_status()
                    content = response.json().get("response", "{}")
                    log_audit(f"VISION_JSON_{current_model}", f"PROMPT:\n{prompt}\n\nRESPONSE:\n{content}")
                    return json.loads(clean_json_string(content))
                
            else:
                # OPENROUTER VISION (Claude 3.5 / GPT-4o)
                or_key = get_system_config("openrouter_api_key", None) or os.getenv("OPENROUTER_API_KEY")
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
                if not response or not getattr(response, "choices", None) or len(response.choices) == 0:
                    raise ValueError(f"Vision model {current_model} returned no choices.")
                return json.loads(response.choices[0].message.content)

        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "too many requests" in err_str:
                success = False
                for attempt in range(3):
                    print(f"  [Vision] Rate Limit 429 on {current_model}. Wait 3s and retry (Attempt {attempt+1}/3)...", flush=True)
                    time.sleep(3)
                    try:
                        if "gemini" in current_model.lower():
                            res = genai.GenerativeModel(current_model).generate_content(msg_content, generation_config={"response_mime_type": "application/json"})
                            content_text = res.text
                        elif "mistral" in current_model.lower() or "pixtral" in current_model.lower():
                            m_slug = current_model.replace("mistral/", "")
                            res = client.chat.complete(model=m_slug, messages=[{"role": "user", "content": mistral_content}], response_format={"type": "json_object"})
                            content_text = res.choices[0].message.content
                        elif "qwen" in current_model.lower() or "ollama" in current_model.lower():
                            res = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=300)
                            content_text = res.json().get("response", "{}")
                        else:
                            res = client.chat.completions.create(model=current_model, messages=[{"role": "user", "content": msg_content}], response_format={"type": "json_object"})
                            content_text = res.choices[0].message.content
                            
                        log_audit(f"VISION_JSON_{current_model}_RETRY", f"PROMPT:\n{prompt}\n\nRESPONSE:\n{content_text}")
                        return json.loads(clean_json_string(content_text))
                    except Exception as inner_e:
                        last_error = inner_e
                
                print(f"  [Vision] {current_model} rate limit persists. Trying next...")
                continue
            else:
                last_error = e
                print(f"  [Vision] {current_model} failed: {e}. Trying next...")
                continue

    # FINAL ATTEMPT: Global Fallback
    fallback = get_system_config("global_fallback_model", "gemini-flash-latest")
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

# ── PREMIUM TIER: Canal dedicado Claude Sonnet ──────────────────────────────
# Estas funciones son exclusivas del tier premium. NO participan del sistema
# de fallback general. Claude Sonnet es el modelo designado, no un fallback.
# Audit log separado: premium_llm_audit.log

PREMIUM_MODEL = "claude-sonnet-4-5"

def log_premium_audit(category: str, data: str):
    """Registro de auditoría exclusivo del tier premium — separado del log general."""
    log_path = os.path.join(os.path.dirname(__file__), "premium_llm_audit.log")
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a") as f:
        f.write(f"\n{'='*80}\n")
        f.write(f"[{timestamp}] [PREMIUM] CATEGORY: {category}\n")
        f.write(f"{data}\n")
        f.write(f"{'='*80}\n")

def generate_premium_json(prompt: str) -> dict:
    """
    PREMIUM DESIGN ENGINE — Claude Sonnet exclusivo.
    Canal dedicado para el tier premium. Sin fallbacks al sistema general.
    Usa ANTHROPIC_API_KEY del .env. Audit log: premium_llm_audit.log
    """
    ant_key = os.getenv("ANTHROPIC_API_KEY")
    if not ant_key:
        raise ValueError("[Premium] ANTHROPIC_API_KEY no configurada en .env")

    print(f"  [Premium LLM] Calling {PREMIUM_MODEL} (dedicated premium channel)...", flush=True)

    client = anthropic.Anthropic(api_key=ant_key)
    response = client.messages.create(
        model=PREMIUM_MODEL,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}]
    )

    raw_text = response.content[0].text if response.content else ""
    log_premium_audit(f"DESIGN_JSON", f"MODEL: {PREMIUM_MODEL}\nPROMPT:\n{prompt[:500]}...\nRESPONSE:\n{raw_text[:1000]}...")

    # Limpiar posibles bloques markdown que Claude a veces incluye
    clean_text = clean_json_string(raw_text)

    # Claude no soporta response_mime_type=json, así que extraemos el JSON manualmente
    # Primero intentamos parsear directamente
    try:
        return json.loads(clean_text)
    except json.JSONDecodeError:
        # Buscar el primer bloque JSON válido en la respuesta
        match = re.search(r'\{.*\}', clean_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"[Premium] Claude no devolvió JSON válido: {clean_text[:300]}")


def generate_premium_vision_json(prompt: str, image_paths: List[str]) -> dict:
    """
    PREMIUM VISION ENGINE — Claude Sonnet exclusivo con visión.
    Canal dedicado para evaluación de fidelidad visual en el tier premium.
    Usa ANTHROPIC_API_KEY del .env. Audit log: premium_llm_audit.log
    """
    import base64

    ant_key = os.getenv("ANTHROPIC_API_KEY")
    if not ant_key:
        raise ValueError("[Premium Vision] ANTHROPIC_API_KEY no configurada en .env")

    print(f"  [Premium Vision] Calling {PREMIUM_MODEL} with {len(image_paths)} image(s)...", flush=True)

    from PIL import Image
    import io

    def prepare_image_b64(path: str, max_size=(1024, 1024)) -> str:
        """Prepara imagen redimensionada en base64 para la API de Anthropic."""
        with Image.open(path) as img:
            img.thumbnail(max_size)
            if img.mode in ("RGBA", "P"):
                bg = Image.new("RGB", img.size, (128, 128, 128))
                bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[3])
                img = bg
            else:
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode("utf-8")

    # Construir el contenido del mensaje con imágenes intercaladas
    msg_content = []
    for path in image_paths:
        if os.path.exists(path):
            img_b64 = prepare_image_b64(path)
            msg_content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": img_b64
                }
            })
    msg_content.append({"type": "text", "text": prompt})

    client = anthropic.Anthropic(api_key=ant_key)
    response = client.messages.create(
        model=PREMIUM_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": msg_content}]
    )

    raw_text = response.content[0].text if response.content else ""
    log_premium_audit(f"VISION_JSON", f"MODEL: {PREMIUM_MODEL}\nIMAGES: {image_paths}\nRESPONSE:\n{raw_text[:1000]}...")

    clean_text = clean_json_string(raw_text)
    try:
        return json.loads(clean_text)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', clean_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"[Premium Vision] Claude no devolvió JSON válido: {clean_text[:300]}")

# ─────────────────────────────────────────────────────────────────────────────

@retry_with_backoff(retries=5)
def get_embeddings_batch(inputs: List[Union[str, bytes]], model: Optional[str] = None) -> List[Optional[list]]:
    """
    UNIVERSAL EMBEDDING ENGINE (v18.6) - Multimodal & Normalized.
    Garantiza salida de 1024 dimensiones para pgvector.
    Supports Text (str) and Images (bytes).
    """
    if not inputs: return []
    
    # 1. Determinar modelos a usar
    # v41.0: Use a more robust chain and fix Gemini names
    model_chain = get_system_config("embedding_model_chain", "mistral-embed,models/gemini-embedding-2")
    
    models_to_try = [m.strip() for m in model_chain.split(",")]
    last_error = None
    
    # Target dimension for the DB
    TARGET_DIM = 1024

    def normalize_vector(vec: list, target: int) -> list:
        """Garantiza la dimensión del vector sin corromper la integridad (v4.0)."""
        current = len(vec)
        if current == target: return vec
        if current > target: return vec[:target] # Truncado es aceptable en algunos modelos
        
        # ERROR: No rellenar con ceros, esto causa 'ceguera vectorial' (Mismatch)
        raise ValueError(f"Vector dimension mismatch: Model returned {current}, but DB requires {target}. Zero-padding is disabled to prevent search blindness.")

    for current_model in models_to_try:
        try:
            print(f"  [Embeddings] Attempting with {current_model}...", flush=True)
            
            if "gemini" in current_model.lower() or "text-embedding" in current_model.lower() or "embedding" in current_model.lower():
                # NATIVE GOOGLE EMBEDDINGS (Text or Multimodal)
                gem_key = get_system_config("gemini_api_key", None) or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
                if not gem_key or genai is None:
                    raise ValueError("Gemini key missing or library not installed")
                genai.configure(api_key=gem_key)
                
                results = []
                for item in inputs:
                    if not item or (isinstance(item, str) and not item.strip()):
                        print("  [Gemini DEBUG] Skipping empty item", flush=True)
                        results.append(None)
                        continue
                        
                    try:
                        # ADAPTADOR INTELIGENTE (v4.0): Forzamos la dimensión a 1024 nativamente
                        m_name = current_model.replace("models/", "")
                        
                        try:
                            if isinstance(item, str):
                                print(f"  [Gemini DEBUG] Embedding string of len {len(item)}", flush=True)
                                res = genai.embed_content(
                                    model=m_name, content=item, 
                                    task_type="retrieval_document",
                                    output_dimensionality=TARGET_DIM
                                )
                            else:
                                print(f"  [Gemini DEBUG] Embedding bytes of len {len(item)}", flush=True)
                                res = genai.embed_content(
                                    model=m_name,
                                    content={'mime_type': 'image/jpeg', 'data': item},
                                    task_type="retrieval_document",
                                    output_dimensionality=TARGET_DIM
                                )
                            
                            results.append(res["embedding"])
                        except Exception as gem_err:
                            if ("not found" in str(gem_err).lower() or "404" in str(gem_err)) and "models/" in m_name:
                                alt_name = m_name.replace("models/", "")
                                print(f"  [Embeddings] 404 with prefix. Retrying with: {alt_name}", flush=True)
                                if isinstance(item, str):
                                    res = genai.embed_content(
                                        model=alt_name, content=item, 
                                        task_type="retrieval_document",
                                        output_dimensionality=TARGET_DIM
                                    )
                                else:
                                    res = genai.embed_content(
                                        model=alt_name,
                                        content={'mime_type': 'image/jpeg', 'data': item},
                                        task_type="retrieval_document",
                                        output_dimensionality=TARGET_DIM
                                    )
                                results.append(res["embedding"])
                            else:
                                print(f"  [Embeddings] Gemini FATAL error (prefix={m_name}): {gem_err}", flush=True)
                                raise gem_err
                    except Exception as e:
                        err_msg = str(e).lower()
                        print(f"  [Embeddings] Item failure in batch: {e}", flush=True)
                        
                        # CRITICAL: If it's a quota or auth error, don't continue the batch.
                        if "429" in err_msg or "quota" in err_msg or "401" in err_msg:
                            print(f"  [Embeddings] FATAL QUOTA/AUTH ERROR DETECTED. Aborting batch.", flush=True)
                            raise e
                            
                        results.append(None)
                
                if any(r is not None for r in results):
                    return results
                else:
                    raise Exception("All items in batch failed for Gemini.")

            elif "mistral" in current_model.lower():
                # MISTRAL EMBEDDINGS (v18.6)
                mis_key = get_system_config("mistral_api_key", None) or os.getenv("MISTRAL_API_KEY")
                if not mis_key: raise ValueError("No Mistral Key")
                from mistralai import Mistral
                client = Mistral(api_key=mis_key)
                
                # Solo texto para Mistral
                text_inputs = [i for i in inputs if isinstance(i, str) and i.strip()]
                print(f"  [Mistral DEBUG] text_inputs length: {len(text_inputs)}", flush=True)
                if not text_inputs: 
                    print("  [Mistral DEBUG] SKIPPING because text_inputs is empty!", flush=True)
                    continue
                
                # Use a higher timeout to prevent hanging
                try:
                    response = client.embeddings.create(
                        model="mistral-embed",
                        inputs=text_inputs
                    )
                except Exception as mis_err:
                    print(f"  [Embeddings] Mistral actual call failed: {mis_err}")
                    raise mis_err
                
                # Mapear resultados respetando el orden original y normalizando a 1024
                final_results = []
                mistral_idx = 0
                for item in inputs:
                    if isinstance(item, str) and item.strip():
                        # Item was sent to Mistral
                        vec = response.data[mistral_idx].embedding
                        final_results.append(normalize_vector(vec, TARGET_DIM))
                        mistral_idx += 1
                    else:
                        # Item was NOT sent (empty string or image)
                        final_results.append(None)
                return final_results

        except Exception as e:
            last_error = e
            print(f"  [Embeddings] {current_model} failed: {e}")
            continue

    raise last_error or Exception("All embedding providers failed.")

def get_embedding(text: str) -> Optional[list]:
    res = get_embeddings_batch([text])
    return res[0] if res else None

@retry_with_backoff(retries=2)
def generate_ai_image(prompt: str) -> Optional[str]:
    """
    Genera una imagen usando Google IMAGEN 4.0 (v8.52 - Protocolo Moderno).
    """
    gem_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not gem_key or google_genai is None:
        print("  [ImageGen] ERROR: Modern SDK or API Key missing.")
        return None

    output_path = f"uploads/ai_v4_{int(time.time())}.png"
    os.makedirs("uploads", exist_ok=True)

    try:
        # v8.65: Audited Imagen 4.0 Call
        print(f"  [ImageGen] INVOKING IMAGEN 4.0: models/imagen-4.0-generate-001 (High Timeout Mode)")
        client = google_genai.Client(api_key=gem_key, http_options={'timeout': 600})
        
        # v8.66: Anti-Diagram & Spelling Protection (Hardened)
        forbidden = ["diagram", "infographic", "text", "chart", "table", "graph", "label", "writing", "logo", "brand"]
        clean_intent = prompt.lower()
        for x in forbidden:
            clean_intent = clean_intent.replace(x, "executive scene")
        
        # v8.67: The "Board-Ready" Aesthetic Protocol
        clean_prompt = (
            f"Professional corporate photography: {clean_intent}. "
            "High-end commercial aesthetic, minimal composition, shallow depth of field. "
            "STRICTLY NO TEXT, NO DIAGRAMS, NO CHARTS, NO LOGOS, NO WRITING ON WALLS. "
            "Clean and architectural."
        )
        
        # LOG AUDIT PRE-CALL
        log_audit("IMAGE_GEN_REQUEST", f"MODEL: imagen-4.0-generate-001\nPROMPT: {clean_prompt}")

        response = client.models.generate_images(
            model='imagen-4.0-generate-001',
            prompt=clean_prompt,
            config=genai_types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="16:9"
            )
        )
        
        if response and response.generated_images:
            img_bytes = response.generated_images[0].image.image_bytes
            with open(output_path, "wb") as f:
                f.write(img_bytes)
            
            # LOG AUDIT SUCCESS
            log_audit("IMAGE_GEN_SUCCESS", f"ASSET CREATED: {output_path}")
            print(f"  [ImageGen] SUCCESS: Created Imagen 4.0 asset: {output_path}")
            return output_path
            
        log_audit("IMAGE_GEN_FAILED", "Response received but no images found.")
        print("  [ImageGen] FAILED: No images in response.")
        return None
        
    except Exception as e:
        print(f"  [ImageGen] API ERROR: {e}")
        return None

def _save_generated_image(data: bytes) -> Optional[str]:
    """Guarda bytes en /uploads."""
    try:
        import uuid
        os.makedirs("uploads", exist_ok=True)
        filename = f"gen_ai_{uuid.uuid4().hex[:8]}.png"
        save_path = os.path.join("uploads", filename)
        with open(save_path, "wb") as f:
            f.write(data)
        print(f"  [ImageGen] SUCCESS! Created: {save_path}")
        return save_path
    except Exception as e:
        print(f"  [ImageGen] Save Error: {e}")
        return None
