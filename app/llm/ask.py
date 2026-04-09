from __future__ import annotations

from app.config import LANGUAGES
from app.llm.languages import get_label


def build_language_instruction() -> str:
    parts: list[str] = []
    for lang in LANGUAGES:
        label = get_label(lang)
        parts.append(f"{label}:\n<answer in {lang}>")
    return "\n\n".join(parts)


def build_answer_system_prompt() -> str:
    return f"""You are a precise knowledge assistant.

Rules:
- Always answer in the following languages:

{build_language_instruction()}

- Keep answers concise
- Use provided notes only
"""
