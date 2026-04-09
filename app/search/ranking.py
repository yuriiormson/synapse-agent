from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import re


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
WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize(text: str) -> str:
    normalized = SEPARATOR_PATTERN.sub(" ", (text or "").lower())
    return WHITESPACE_PATTERN.sub(" ", normalized).strip()


def tokenize(text: str) -> list[str]:
    return [token for token in normalize(text).split() if token]


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def score(query_tokens: list[str], doc_tokens: list[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0

    total = 0.0
    for query_token in query_tokens:
        best = 0.0
        for doc_token in doc_tokens:
            candidate = similarity(query_token, doc_token)
            if candidate > best:
                best = candidate
        total += best
    return total


def _build_preview(text: str, *, max_length: int) -> str:
    collapsed = re.sub(r"\s+", " ", (text or "")).strip()
    return collapsed[:max_length].strip()


def _score_note(query: str, query_tokens: list[str], note: IndexedNote) -> float:
    normalized_query = normalize(query)
    normalized_title = normalize(note.title)
    title_tokens = tokenize(note.title)

    tag_tokens: list[str] = []
    for tag in note.tags:
        tag_tokens.extend(tokenize(tag))

    content_tokens = tokenize(f"{note.body}\n{note.metadata_text}")

    title_score = score(query_tokens, title_tokens) * 10
    tag_score = score(query_tokens, tag_tokens) * 5
    content_score = score(query_tokens, content_tokens)

    if normalized_query and normalized_query in normalized_title:
        title_score += 5

    return title_score + tag_score + content_score


def rank_notes(
    query: str,
    notes: list[IndexedNote],
    base_path: Path,
    *,
    limit: int,
    snippet_length: int = 120,
) -> list[SearchResult]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    results: list[SearchResult] = []
    for note in notes:
        note_score = _score_note(query, query_tokens, note)
        if note_score <= 0.3:
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
                score=round(note_score, 2),
                modified_at=note.modified_at,
            )
        )

    results.sort(key=lambda item: (-item.score, -item.modified_at, item.relative_path))
    return results[:limit]
