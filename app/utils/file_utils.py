from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml


INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
INLINE_TAGS = re.compile(r"(?:^|\s)#([A-Za-z0-9_/\-]+)")
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]{2,}")
VALID_TYPES = {"project", "area", "resource", "archive"}
WHITESPACE = re.compile(r"\s+")


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class NoteDocument:
    path: Path
    raw_text: str
    body: str
    frontmatter: dict[str, Any]
    has_frontmatter: bool
    frontmatter_valid: bool
    frontmatter_errors: list[str]
    title: str
    tags: list[str]
    modified_at: float


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.exception("Failed to read file: %s", path)
        raise RuntimeError(f"Could not read file: {path}") from exc


def write_text(path: Path, text: str) -> None:
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        logger.exception("Failed to write file: %s", path)
        raise RuntimeError(f"Could not write file: {path}") from exc


def sanitize_folder_name(value: str, *, default: str = "General") -> str:
    cleaned = INVALID_PATH_CHARS.sub(" ", value or "")
    cleaned = WHITESPACE.sub(" ", cleaned).strip(" .")
    return cleaned[:80] or default


def extract_title(path: str | Path) -> str:
    name = Path(path).name
    if name.lower().endswith(".md"):
        name = name[:-3]
    return name.replace("_", " ").strip()


def relative_to_base(path: Path, base_path: Path) -> str:
    try:
        return path.resolve().relative_to(base_path.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def iter_markdown_files(base_path: Path) -> list[Path]:
    if not base_path.exists():
        return []
    return sorted(path for path in base_path.rglob("*.md") if path.is_file())


def build_destination_path(target_dir: Path, file_name: str) -> Path:
    destination = target_dir / file_name
    if not destination.exists():
        return destination

    source = Path(file_name)
    counter = 1
    while True:
        candidate = target_dir / f"{source.stem}-{counter}{source.suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str, bool, bool]:
    if not text.startswith("---\n"):
        return {}, text, False, False

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, False, False

    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() in {"---", "..."}:
            end_index = index
            break

    if end_index is None:
        return {}, text, True, False

    raw_frontmatter = "\n".join(lines[1:end_index])
    body = "\n".join(lines[end_index + 1 :]).lstrip("\n")

    try:
        parsed = yaml.safe_load(raw_frontmatter) or {}
    except yaml.YAMLError:
        return {}, body, True, False

    if not isinstance(parsed, dict):
        return {}, body, True, False

    return parsed, body, True, True


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key).lower(): _json_safe(item) for key, item in value.items()}
    return str(value)


def normalize_frontmatter(frontmatter: dict[str, Any]) -> dict[str, Any]:
    return {str(key).lower(): _json_safe(value) for key, value in frontmatter.items()}


def validate_frontmatter(frontmatter: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    string_like_fields = {
        "title",
        "section",
        "para",
        "pillar",
        "bucket",
        "folder_section",
        "type",
        "project",
        "initiative",
        "client",
        "milestone",
        "workstream",
        "area",
        "domain",
        "responsibility",
        "owner",
        "resource",
        "topic",
        "subject",
        "category",
        "reference",
        "source",
        "status",
        "archive_bucket",
    }

    for key in string_like_fields:
        value = frontmatter.get(key)
        if value is None:
            continue
        if isinstance(value, (list, dict)):
            errors.append(f"{key} must be a single string-like value")

    tags_value = frontmatter.get("tags")
    if tags_value is not None and not isinstance(tags_value, (str, list, tuple, set)):
        errors.append("tags must be a string or list")

    type_value = frontmatter.get("type")
    if type_value is None:
        errors.append("type is required")
    elif not isinstance(type_value, str):
        errors.append("type must be a string")
    elif type_value.strip().lower() not in VALID_TYPES:
        errors.append(f"type must be one of: {', '.join(sorted(VALID_TYPES))}")

    return errors


def ensure_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,;]", value)
    elif isinstance(value, (list, tuple, set)):
        parts = [str(item) for item in value]
    else:
        parts = [str(value)]

    items: list[str] = []
    for part in parts:
        cleaned = WHITESPACE.sub(" ", str(part)).strip()
        if cleaned and cleaned not in items:
            items.append(cleaned)
    return items


def extract_inline_tags(text: str) -> list[str]:
    tags: list[str] = []
    for match in INLINE_TAGS.findall(text):
        cleaned = match.strip()
        if cleaned and cleaned not in tags:
            tags.append(cleaned)
    return tags


def read_note(path: Path) -> NoteDocument:
    raw_text = read_text(path)
    frontmatter, body, has_frontmatter, frontmatter_valid = _parse_frontmatter(raw_text)
    normalized_frontmatter = normalize_frontmatter(frontmatter)
    frontmatter_errors = validate_frontmatter(normalized_frontmatter) if frontmatter_valid else []
    frontmatter_valid = frontmatter_valid and not frontmatter_errors
    frontmatter_tags = ensure_string_list(normalized_frontmatter.get("tags"))
    inline_tags = extract_inline_tags(body)

    tags: list[str] = []
    for tag in frontmatter_tags + inline_tags:
        normalized = tag.strip()
        if normalized and normalized not in tags:
            tags.append(normalized)

    title = str(normalized_frontmatter.get("title") or path.stem).strip() or path.stem
    try:
        modified_at = path.stat().st_mtime
    except OSError as exc:
        logger.exception("Failed to stat file: %s", path)
        raise RuntimeError(f"Could not access file metadata: {path}") from exc

    return NoteDocument(
        path=path,
        raw_text=raw_text,
        body=body,
        frontmatter=normalized_frontmatter,
        has_frontmatter=has_frontmatter,
        frontmatter_valid=frontmatter_valid,
        frontmatter_errors=frontmatter_errors,
        title=title,
        tags=tags,
        modified_at=modified_at,
    )


def metadata_to_text(metadata: dict[str, Any]) -> str:
    pieces: list[str] = []
    for key, value in metadata.items():
        if isinstance(value, list):
            rendered = " ".join(str(item) for item in value)
        elif isinstance(value, dict):
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            rendered = str(value)
        pieces.append(f"{key} {rendered}")
    return " ".join(pieces).strip()


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text.lower())]


def build_snippet(text: str, terms: list[str], *, max_length: int = 220) -> str:
    collapsed = WHITESPACE.sub(" ", text or "").strip()
    if not collapsed:
        return ""

    lowered = collapsed.lower()
    anchor = 0
    for term in terms:
        position = lowered.find(term.lower())
        if position >= 0:
            anchor = position
            break

    sentence_start = max(lowered.rfind(". ", 0, anchor), lowered.rfind("! ", 0, anchor), lowered.rfind("? ", 0, anchor))
    if sentence_start >= 0:
        anchor = sentence_start + 1

    start = max(anchor - max_length // 4, 0)
    end = min(start + max_length, len(collapsed))
    snippet = collapsed[start:end].strip()
    if start > 0:
        snippet = f"...{snippet}"
    if end < len(collapsed):
        snippet = f"{snippet}..."
    return snippet


def chunk_text(text: str, *, max_length: int = 3500) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return [""]
    if len(normalized) <= max_length:
        return [normalized]

    chunks: list[str] = []
    remaining = normalized
    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n", 0, max_length)
        if split_at < max_length // 2:
            split_at = remaining.rfind(" ", 0, max_length)
        if split_at < max_length // 2:
            split_at = max_length

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return chunks
