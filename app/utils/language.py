from __future__ import annotations


def detect_language(text: str) -> str:
    lowered = (text or "").lower()

    ua_chars = set("іїєґ")
    if any(char in lowered for char in ua_chars):
        return "uk"

    return "en"
