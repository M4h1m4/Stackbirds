"""Thin OpenAI client wrapper for LLM calls (questions, matching, decision)."""

import json
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from backend.config import get_config
from backend.models import LLMThoughtEntry


def get_openai_client() -> Optional[OpenAI]:
    """Return OpenAI client if API key is set, else None."""
    config = get_config()
    if not config.openai_api_key:
        return None
    return OpenAI(api_key=config.openai_api_key)


def get_model() -> str:
    return get_config().openai_model


def call_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    response_format: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Optional[LLMThoughtEntry]]:
    """
    Call OpenAI chat completion. Returns (content_text, llm_thought_entry for audit).
    If client is missing or call fails, returns ("", None) or raises.
    """
    client = get_openai_client()
    if not client:
        return "", None
    model = get_model()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    kwargs: Dict[str, Any] = {"model": model, "messages": messages}
    if response_format:
        kwargs["response_format"] = response_format
    resp = client.chat.completions.create(**kwargs)
    choice = resp.choices[0] if resp.choices else None
    content = (choice.message.content or "").strip() if choice else ""
    # Build audit entry (thoughts = full response for audit trail)
    thought = LLMThoughtEntry(
        phase="LLM",
        step="call",
        thoughts=content,
        input_summary=user_prompt[:500] + ("..." if len(user_prompt) > 500 else ""),
        output_summary=content[:300] + ("..." if len(content) > 300 else ""),
    )
    return content, thought


def parse_json_array_from_llm(content: str) -> List[Dict[str, str]]:
    """Parse JSON array of objects from LLM output; return [] on failure."""
    content = content.strip()
    # Try to find a JSON array in the response
    start = content.find("[")
    if start == -1:
        return []
    depth = 0
    end = -1
    for i in range(start, len(content)):
        if content[i] == "[":
            depth += 1
        elif content[i] == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        return []
    try:
        arr = json.loads(content[start:end])
        if not isinstance(arr, list):
            return []
        return [{"id": str(x.get("id", i)), "text": str(x.get("text", ""))} for i, x in enumerate(arr) if isinstance(x, dict)]
    except json.JSONDecodeError:
        return []
