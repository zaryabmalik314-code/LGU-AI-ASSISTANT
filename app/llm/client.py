"""
Thin wrapper around Groq API (OpenAI-compatible). Single responsibility:
send a prompt, get text back. No business logic here — that lives in explain.py.
"""
import json
import urllib.request
import urllib.error
from app.config import settings

GROQ_API_KEY = settings.groq_api_key
API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"


class LLMError(Exception):
    """Raised on any API failure — caller should catch this and use fallback template."""
    pass


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 1024, temperature: float = 0.2) -> str:
    if not GROQ_API_KEY:
        raise LLMError("GROQ_API_KEY not set")

    payload = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},  # Groq JSON mode — enforces valid JSON output
    }

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise LLMError(f"API request failed: {e}")
    except json.JSONDecodeError as e:
        raise LLMError(f"Invalid JSON response: {e}")

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"Unexpected API response shape: {e}")

    if not text.strip():
        raise LLMError("Empty response from LLM")

    return text
