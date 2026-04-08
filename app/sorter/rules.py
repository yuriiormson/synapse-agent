from __future__ import annotations

from typing import Any

from app.config import SETTINGS
from app.utils.file_utils import ensure_string_list, sanitize_folder_name


SECTIONS = {
    "Projects": "Projects",
    "Areas": "Areas",
    "Resources": "Resources",
    "Archives": "Archives",
}

SECTION_ALIASES = {
    "projects": "Projects",
    "project": "Projects",
    "1. projects": "Projects",
    "areas": "Areas",
    "area": "Areas",
    "2. areas": "Areas",
    "resources": "Resources",
    "resource": "Resources",
    "3. resources": "Resources",
    "archives": "Archives",
    "archive": "Archives",
    "4. archives": "Archives",
}

PROJECT_TYPES = {
    "project",
    "initiative",
    "milestone",
    "client-project",
    "deliverable",
}

AREA_TYPES = {
    "area",
    "responsibility",
    "domain",
    "role",
    "life-area",
}

RESOURCE_TYPES = {
    "resource",
    "reference",
    "note",
    "article",
    "book",
    "research",
    "idea",
    "meeting",
    "document",
}

ARCHIVE_STATUSES = {
    "archived",
    "archive",
    "done",
    "complete",
    "completed",
    "closed",
    "cancelled",
}


def normalize_section(value: str | None) -> str | None:
    if not value:
        return None
    return SECTION_ALIASES.get(str(value).strip().lower())


def section_directory(section: str) -> str:
    return SECTIONS.get(section, SECTIONS["Resources"])


def nearest_valid_section(section: str | None) -> str:
    return section if section in SECTIONS else "Resources"


def default_unsorted_folder() -> str:
    return sanitize_folder_name(SETTINGS.unsorted_folder_name, default="Unsorted")


def folder_creation_allowed(section: str) -> bool:
    return section in {"Projects", "Areas", "Resources"}


def normalized_tags(value: Any) -> list[str]:
    return [tag.lower() for tag in ensure_string_list(value)]
