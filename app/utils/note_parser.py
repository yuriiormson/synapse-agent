from __future__ import annotations

import json
import re
from typing import Any

import yaml


STRUCTURED_NOTE_PATTERN = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def parse_structured_note(text: str) -> tuple[dict[str, Any] | None, str]:
    match = STRUCTURED_NOTE_PATTERN.search(text)
    if not match:
        return None, text

    try:
        metadata = json.loads(match.group(1))
    except Exception:
        return None, text

    if not isinstance(metadata, dict):
        return None, text

    before = text[: match.start()].strip()
    after = text[match.end() :].strip()
    body = "\n\n".join(part for part in (before, after) if part).strip()
    return metadata, body


def metadata_to_yaml(meta: dict[str, Any]) -> str:
    payload = {
        str(key): value
        for key, value in meta.items()
        if str(key).strip().lower() != "filename"
    }
    payload.setdefault("type", "resource")
    payload.setdefault("source", "telegram")
    return f"---\n{yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).strip()}\n---\n"
