from __future__ import annotations

import json
import logging
from typing import Any

import requests

from app.config import SETTINGS
from app.llm.ask import build_answer_system_prompt


logger = logging.getLogger(__name__)


CLASSIFICATION_SYSTEM_PROMPT = """You classify markdown notes for a local PARA vault.

Rules:
- Return strict JSON only.
- section must be one of: Projects, Areas, Resources, Archives.
- folder must be a concise folder name.
- create_folder must be a JSON boolean.
- tags must be a JSON array of short strings.
- No markdown fences, no explanations.
"""

def _extract_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("LLM response did not include choices.")

    message = choices[0].get("message", {})
    content = message.get("content")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        joined = "".join(parts).strip()
        if joined:
            return joined

    raise RuntimeError("LLM response did not include text content.")


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    inner = [line for line in lines if not line.startswith("```")]
    return "\n".join(inner).strip()


def _chat_completion(
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
) -> str:
    logger.info("LLM call to %s using model %s", SETTINGS.llm_api, SETTINGS.llm_model)
    try:
        response = requests.post(
            SETTINGS.llm_api,
            json={
                "model": SETTINGS.llm_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=SETTINGS.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.error("LLM request failed: %s", exc, exc_info=True)
        raise RuntimeError("Local LLM request failed.") from exc

    return _extract_content(payload)


def classify_note_fallback(
    text: str,
    metadata: dict[str, Any],
    title: str,
) -> dict[str, Any]:
    metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    prompt = f"""
Classify this note into PARA only because metadata was insufficient.

Return ONLY JSON:
{{
  "section": "Projects|Areas|Resources|Archives",
  "folder": "string",
  "create_folder": true,
  "tags": ["tag"]
}}

Prefer Resources when uncertain.

Title:
{title}

Metadata:
{metadata_json}

Note:
{text}
""".strip()

    content = _strip_fences(
        _chat_completion(
            [
                {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=SETTINGS.llm_max_tokens,
            temperature=0,
        )
    )
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise RuntimeError("LLM classification payload must be a JSON object.")
    return payload


def answer_query(query: str, contexts: list[dict[str, str]]) -> str:
    if not contexts:
        raise ValueError("At least one note context is required.")

    rendered_context = "\n\n".join(
        (
            f"Source {index + 1}: {item['path']}\n"
            f"Title: {item['title']}\n"
            f"Snippet: {item['snippet']}\n"
            f"Excerpt:\n{item['content']}"
        )
        for index, item in enumerate(contexts)
    )
    prompt = f"""
Question:
{query}

Use only these local notes:

{rendered_context}

Provide a short grounded answer. Mention uncertainty if the notes do not fully answer the question.
""".strip()

    return _chat_completion(
        [
            {"role": "system", "content": build_answer_system_prompt()},
            {"role": "user", "content": prompt},
        ],
        max_tokens=SETTINGS.llm_max_tokens,
        temperature=0.1,
    ).strip()
