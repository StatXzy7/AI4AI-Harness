"""Generate multiple candidate SQL queries and select the best executable candidate."""
# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


def _as_text(response):
    if response is None:
        return ""
    if isinstance(response, bytes):
        return response.decode("utf-8", "ignore")
    if isinstance(response, str):
        return response
    if isinstance(response, (list, tuple)):
        for item in response:
            text = _as_text(item)
            if text.strip():
                return text
        return ""
    if isinstance(response, dict):
        for key in (
            "choices",
            "candidates",
            "results",
            "outputs",
            "text",
            "completion",
            "content",
            "sql",
            "message",
            "output",
        ):
            if key in response:
                text = _as_text(response[key])
                if text.strip():
                    return text
        return ""
    return str(response)


def _response_texts(response):
    if response is None:
        return []
    if isinstance(response, (list, tuple)):
        texts = []
        for item in response:
            texts.extend(_response_texts(item))
        return texts
    if isinstance(response, dict):
        for key in ("choices", "candidates", "results", "outputs"):
            if key in response:
                return _response_texts(response[key])
        text = _as_text(response)
        return [text] if text.strip() else []
    text = _as_text(response)
    return [text] if text.strip() else []


def _extract_sql(text):
    if not text:
        return ""

    candidate = ""
    try:
        candidate = bridge.extract_sql(text) or ""
    except Exception:
        candidate = ""

    candidate = str(candidate).strip()
    if candidate:
        return candidate.rstrip(";").strip()

    cleaned = str(text).strip()
    if cleaned.startswith("