from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from app.utils.file_utils import tokenize


@dataclass(slots=True)
class IndexedNote:
    path: str
    title: str
    section: str
    folder: str
    tags: list[str]
    body: str
    metadata_text: str
    modified_at: float


@dataclass(slots=True)
class SearchResult:
    path: Path
    relative_path: str
    title: str
    section: str
    folder: str
    tags: list[str]
    snippet: str
    score: float
    modified_at: float


SEPARATOR_PATTERN = re.compile(r"[-_/]+")


def _normalize_text(value: str) -> str:
    return SEPARATOR_PATTERN.sub(" ", (value or "").lower()).strip()


def _matches_by_term(text: str, terms: list[str]) -> int:
    return sum(1 for term in terms if term in text)


def _build_preview(text: str, *, max_length: int) -> str:
    collapsed = re.sub(r"\s+", " ", (text or "")).strip()
    return collapsed[:max_length].strip()


def _score_note(query: str, terms: list[str], note: IndexedNote) -> float:
    phrase = _normalize_text(query)
    title = _normalize_text(note.title)
    content = _normalize_text(f"{note.body}\n{note.metadata_text}")
    tags = [_normalize_text(tag) for tag in note.tags]

    title_score = 0.0
    tag_score = 0.0
    content_score = 0.0

    if phrase and phrase in title:
        title_score += 10
    title_score += _matches_by_term(title, terms) * 3

    for tag in tags:
        if phrase and phrase in tag:
            tag_score += 5
        tag_score += _matches_by_term(tag, terms) * 2

    if phrase and phrase in content:
        content_score += 1
    content_score += _matches_by_term(content, terms)

    return title_score + tag_score + content_score


def rank_notes(
    query: str,
    notes: list[IndexedNote],
    base_path: Path,
    *,
    limit: int,
    snippet_length: int = 120,
) -> list[SearchResult]:
    terms = tokenize(query)
    if not terms:
        return []

    results: list[SearchResult] = []
    for note in notes:
        score = _score_note(query, terms, note)
        if score <= 0:
            continue

        snippet_source = note.body or note.metadata_text or note.title
        results.append(
            SearchResult(
                path=base_path / note.path,
                relative_path=note.path,
                title=note.title,
                section=note.section,
                folder=note.folder,
                tags=note.tags,
                snippet=_build_preview(snippet_source, max_length=snippet_length),
                score=round(score, 2),
                modified_at=note.modified_at,
            )
        )

    results.sort(key=lambda item: (-item.score, -item.modified_at, item.relative_path))
    return results[:limit]
