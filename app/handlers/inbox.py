from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from app.utils.file_utils import build_destination_path, write_text
from app.utils.folders import resolve_folder
from app.utils.note_parser import metadata_to_yaml, parse_structured_note


INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def _sanitize_filename(value: str) -> str:
    cleaned = INVALID_FILENAME.sub("", value or "")
    cleaned = cleaned.replace(".md", "").strip().strip(".")
    return cleaned[:80] or "note"


def _default_filename(created_at: datetime) -> str:
    return f"note_{created_at.strftime('%Y%m%d_%H%M%S')}"


def save_to_inbox(vault_path: str | Path, text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Telegram text message was empty.")

    inbox_path = resolve_folder(vault_path, "inbox")
    created_at = datetime.now(timezone.utc)
    metadata, body = parse_structured_note(cleaned)

    if metadata:
        raw_filename = str(metadata.get("filename") or "").strip()
        filename = _sanitize_filename(raw_filename or _default_filename(created_at))
        yaml_block = metadata_to_yaml(metadata)
        content = f"{yaml_block}\n{(body or '').strip()}\n"
    else:
        filename = _default_filename(created_at)
        content = f"{cleaned}\n"

    file_path = build_destination_path(inbox_path, f"{filename}.md")
    write_text(file_path, content)
    return str(file_path)
