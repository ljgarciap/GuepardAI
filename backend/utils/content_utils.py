import ast
import re

_BULLET_PREFIX_RE = re.compile(r'^[\-\*\•\·\–\—\>]\s*')


def normalize_bullets(bullets_list) -> list:
    if not bullets_list:
        return []
    result = []
    for b in bullets_list:
        if isinstance(b, dict):
            text = b.get("text") or b.get("description") or b.get("priority") or " - ".join(str(v) for v in b.values() if v)
        else:
            text = str(b)
        text = _BULLET_PREFIX_RE.sub("", text.strip()).strip()
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
