import ast
import re

_BULLET_PREFIX_RE = re.compile(r'^[\-\*\•\·\–\—\>]\s*')


# Multi-word bracketed placeholders: [CEO Name], [Retailer CEO Name], [Company Name]
_BRACKET_MULTIWORD_RE = re.compile(r'\[[A-Z][a-zA-Z]+(?:\s[A-Za-z]+)+\]')
# Known single-word placeholder terms LLMs commonly produce
_BRACKET_KEYWORD_RE = re.compile(
    r'\[(?:Company|Year|Name|Date|City|Region|Client|CEO|Manager|Title'
    r'|Person|Brand|Product|Location|Contact|Team|Leader|Director|President)\]'
)


def sanitize_text_field(text: str) -> str:
    """Strip inline Markdown and LLM-generated bracket placeholders from plain-text fields."""
    if not isinstance(text, str) or not text:
        return text or ""
    text = re.sub(r'\*{2}([^*]*)\*{2}', r'\1', text)        # **bold** → bold
    text = re.sub(r'_{2}([^_]*)_{2}', r'\1', text)          # __bold__ → bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)               # *italic* → italic
    text = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'\1', text)   # _italic_ (not word-internal)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)     # [text](url) → text
    text = re.sub(r'`([^`]+)`', r'\1', text)                 # `code` → code
    text = re.sub(r'^#{1,6}\s+', '', text)                   # # Heading → Heading
    text = _BRACKET_MULTIWORD_RE.sub('', text)               # [CEO Name] → ''
    text = _BRACKET_KEYWORD_RE.sub('', text)                 # [Company] → ''
    text = re.sub(r'\*+', '', text)                           # residual asterisks
    return text.strip()


def normalize_bullets(bullets_list) -> list:
    if not bullets_list:
        return []
    result = []
    for b in bullets_list:
        if isinstance(b, dict):
            text = b.get("text") or b.get("description") or b.get("priority") or " - ".join(str(v) for v in b.values() if v)
        else:
            text = str(b)
        text = sanitize_text_field(text.strip())  # strip inline markdown before prefix removal
        text = _BULLET_PREFIX_RE.sub("", text).strip()
        if text:
            result.append(text)
    return result


def normalize_metrics(metrics_list) -> list:
    if not metrics_list:
        return []
    result = []
    for m in metrics_list:
        if isinstance(m, dict):
            result.append(m)
        elif isinstance(m, str):
            try:
                parsed = ast.literal_eval(m.strip())
                if isinstance(parsed, dict):
                    result.append(parsed)
                else:
                    result.append({"label": m.strip(), "value": ""})
            except Exception:
                result.append({"label": m.strip(), "value": ""})
        else:
            result.append({"label": str(m).strip(), "value": ""})
    return result
