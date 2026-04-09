from __future__ import annotations

from app.config import AUTO_LANGUAGE, LLM_LANGUAGES
from app.llm.languages import get_label
from app.utils.language import detect_language


def build_language_block(langs: list[str]) -> str:
    parts: list[str] = []
    for lang in langs:
        label = get_label(lang)
        parts.append(f"{label}:\n<answer in {lang}>")
    return "\n\n".join(parts)


def _resolve_languages(query: str) -> list[str]:
    query_lang = detect_language(query)

    if LLM_LANGUAGES:
        langs = [lang.strip() for lang in LLM_LANGUAGES.split(",") if lang.strip()]
    elif AUTO_LANGUAGE:
        langs = [query_lang]
    else:
        langs = ["en"]

    return langs or ["en"]


def build_answer_system_prompt(query: str) -> str:
    langs = _resolve_languages(query)
    language_instruction = build_language_block(langs)

    extra_rule = ""
    if langs == [detect_language(query)]:
        extra_rule = "\n- If only one language is requested, answer once in that language only"

    return f"""You are a precise knowledge assistant.

Rules:
- Answer using ONLY the provided notes
- Be concise and factual{extra_rule}

Respond in:

{language_instruction}
"""
