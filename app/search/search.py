from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from app.config import SETTINGS
from app.search.ranking import IndexedNote, SearchResult, rank_notes
from app.sorter.rules import normalize_section
from app.utils.file_utils import (
    iter_markdown_files,
    metadata_to_text,
    read_note,
    relative_to_base,
)


logger = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS notes_index (
    path TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    section TEXT NOT NULL,
    folder TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    body TEXT NOT NULL,
    metadata_text TEXT NOT NULL,
    modified_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notes_section ON notes_index(section);
CREATE INDEX IF NOT EXISTS idx_notes_folder ON notes_index(folder);
CREATE INDEX IF NOT EXISTS idx_notes_modified_at ON notes_index(modified_at);

CREATE TABLE IF NOT EXISTS user_sessions (
    user_id INTEGER PRIMARY KEY,
    results_json TEXT NOT NULL,
    timestamp REAL NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(SETTINGS.index_db_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_index() -> None:
    SETTINGS.index_db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as connection:
        connection.executescript(SCHEMA)


def _section_and_folder(relative_path: str) -> tuple[str, str]:
    parts = Path(relative_path).parts
    raw_section = parts[0] if parts else ""
    section = normalize_section(raw_section) or raw_section or "Resources"
    folder = parts[1] if len(parts) > 2 else ""
    return section, folder


def refresh_index(base_path: str | Path) -> int:
    base = Path(base_path).expanduser()
    initialize_index()

    indexed = 0
    with _connect() as connection:
        connection.execute("DELETE FROM notes_index")
        for path in iter_markdown_files(base):
            try:
                note = read_note(path)
            except RuntimeError as exc:
                logger.warning("Skipping note during indexing: %s", exc)
                continue
            relative_path = relative_to_base(path, base)
            section, folder = _section_and_folder(relative_path)
            connection.execute(
                """
                INSERT INTO notes_index(path, title, section, folder, tags_json, body, metadata_text, modified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    relative_path,
                    note.title,
                    section,
                    folder,
                    json.dumps(note.tags, ensure_ascii=False),
                    note.body,
                    metadata_to_text(note.frontmatter),
                    note.modified_at,
                ),
            )
            indexed += 1
    return indexed


def _read_index() -> list[IndexedNote]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT path, title, section, folder, tags_json, body, metadata_text, modified_at
            FROM notes_index
            """
        ).fetchall()

    notes: list[IndexedNote] = []
    for row in rows:
        try:
            tags = json.loads(row["tags_json"])
        except json.JSONDecodeError:
            tags = []

        notes.append(
            IndexedNote(
                path=row["path"],
                title=row["title"],
                section=row["section"],
                folder=row["folder"],
                tags=tags,
                body=row["body"],
                metadata_text=row["metadata_text"],
                modified_at=float(row["modified_at"]),
            )
        )
    return notes


def search(query: str, base_path: str | Path, limit: int = 5) -> list[SearchResult]:
    normalized_query = query.strip()
    if not normalized_query:
        return []

    logger.info("Search query: %s", normalized_query)
    base = Path(base_path).expanduser()
    refresh_index(base)
    notes = _read_index()
    results = rank_notes(
        normalized_query,
        notes,
        base,
        limit=limit,
        snippet_length=min(SETTINGS.search_snippet_chars, 120),
    )
    logger.info("Search returned %s results for query: %s", len(results), normalized_query)
    return results


def save_user_session(user_id: int, results: list[SearchResult]) -> None:
    initialize_index()
    payload = [
        {
            "relative_path": item.relative_path,
            "title": item.title,
            "section": item.section,
            "folder": item.folder,
            "tags": item.tags,
            "snippet": item.snippet,
            "score": item.score,
            "modified_at": item.modified_at,
        }
        for item in results
    ]
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO user_sessions(user_id, results_json, timestamp)
            VALUES (?, ?, strftime('%s', 'now'))
            ON CONFLICT(user_id) DO UPDATE SET
                results_json = excluded.results_json,
                timestamp = excluded.timestamp
            """,
            (user_id, json.dumps(payload, ensure_ascii=False)),
        )


def load_user_session(user_id: int, base_path: str | Path) -> list[SearchResult]:
    initialize_index()
    base = Path(base_path).expanduser()
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT results_json
            FROM user_sessions
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

    if row is None:
        return []

    try:
        payload = json.loads(row["results_json"])
    except json.JSONDecodeError:
        logger.error("Stored session for user %s is invalid JSON.", user_id)
        return []

    results: list[SearchResult] = []
    for item in payload:
        relative_path = str(item.get("relative_path") or "").strip()
        if not relative_path:
            continue
        results.append(
            SearchResult(
                path=base / relative_path,
                relative_path=relative_path,
                title=str(item.get("title") or Path(relative_path).stem),
                section=str(item.get("section") or ""),
                folder=str(item.get("folder") or ""),
                tags=[str(tag) for tag in item.get("tags") or []],
                snippet=str(item.get("snippet") or ""),
                score=float(item.get("score") or 0.0),
                modified_at=float(item.get("modified_at") or 0.0),
            )
        )
    return results
