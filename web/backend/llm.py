"""Tiny OpenAI chat-JSON helper, reused for brief parsing and per-candidate judging.

Mirrors the robust call pattern from extract_entities.py: strict json_schema output,
reasoning_effort=minimal for gpt-5/o models, and adaptive fallback for param quirks.
"""
import json

import dataroot  # noqa: F401
import config
import httputil


def chat_json(model: str, system: str, user: str, schema: dict,
              reasoning: str = "minimal", max_tokens: int = 1200) -> dict:
    key = config.openai_key()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "result", "strict": True, "schema": schema}},
        "max_completion_tokens": max_tokens,
    }
    if reasoning and (model.startswith("gpt-5") or model.startswith("o")):
        payload["reasoning_effort"] = reasoning
    headers = {"Authorization": f"Bearer {key}"}

    status, body = httputil.post_json(f"{config.OPENAI_BASE}/chat/completions",
                                      payload, headers=headers, timeout=90)
    if status == 400 and isinstance(body, dict):
        msg = str(body.get("error", {}).get("message", "")).lower()
        changed = False
        if "max_completion_tokens" in msg or "max_tokens" in msg:
            payload["max_tokens"] = payload.pop("max_completion_tokens", max_tokens)
            changed = True
        if "reasoning_effort" in msg or "reasoning" in msg:
            payload.pop("reasoning_effort", None)
            changed = True
        if changed:
            status, body = httputil.post_json(f"{config.OPENAI_BASE}/chat/completions",
                                              payload, headers=headers, timeout=90)
    if status != 200:
        raise RuntimeError(f"openai {status}: {str(body)[:300]}")
    choice = body["choices"][0]
    content = (choice.get("message", {}) or {}).get("content") or ""
    if not content.strip():
        raise RuntimeError(f"empty completion (finish_reason={choice.get('finish_reason')})")
    return json.loads(content)
