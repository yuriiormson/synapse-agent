from __future__ import annotations


LANG_LABELS = {
    "en": "EN",
    "uk": "UA",
    "pl": "PL",
    "de": "DE",
}


def get_label(lang: str) -> str:
    return LANG_LABELS.get(lang, str(lang).upper())
