from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import math

from app.utils.file_utils import build_snippet, tokenize


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


def _count_matches(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(lowered.count(term) for term in terms)


def _recency_score(modified_at: float) -> float:
    age_days = max(
        (datetime.now(timezone.utc).timestamp() - modified_at) / 86400,
        0,
    )
    if age_days <= 7:
        return 2.5
    if age_days <= 30:
        return 1.5
    return max(0.0, 1.0 - math.log10(age_days + 1) / 3)


def _score_note(query: str, terms: list[str], note: IndexedNote) -> float:
    title = note.title.lower()
    path = note.path.lower()
    folder = note.folder.lower()
    section = note.section.lower()
    body = note.body.lower()
    metadata = note.metadata_text.lower()
    tags = [tag.lower() for tag in note.tags]

    phrase = query.lower()
    keyword_score = 0.0
    tag_score = 0.0
    folder_score = 0.0

    keyword_score += _count_matches(title, terms)
    keyword_score += _count_matches(body, terms)
    keyword_score += _count_matches(metadata, terms)

    tag_score += sum(
        1
        for term in terms
        for tag in tags
        if term in tag
    )

    folder_score += _count_matches(folder, terms)
    folder_score += _count_matches(section, terms)
    folder_score += _count_matches(path, terms)

    score = keyword_score * 2 + tag_score * 3 + folder_score * 2 + _recency_score(note.modified_at)

    if phrase in title:
        score += 5

    if phrase == title or phrase == path or phrase == folder:
        score += 3

    if phrase in metadata:
        score += 2

    if phrase in body:
        score += 1

    return score


def rank_notes(
    query: str,
    notes: list[IndexedNote],
    base_path: Path,
    *,
    limit: int,
    snippet_length: int = 220,
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
                snippet=build_snippet(snippet_source, terms, max_length=snippet_length),
                score=round(score, 2),
                modified_at=note.modified_at,
            )
        )

    results.sort(key=lambda item: (-item.score, -item.modified_at, item.relative_path))
    return results[:limit]
