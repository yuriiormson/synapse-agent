from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from app.llm.client import classify_note_fallback
from app.sorter.rules import (
    ARCHIVE_STATUSES,
    AREA_TYPES,
    PROJECT_TYPES,
    RESOURCE_TYPES,
    default_unsorted_folder,
    folder_creation_allowed,
    nearest_valid_section,
    normalize_section,
    normalized_tags,
)
from app.utils.file_utils import NoteDocument, ensure_string_list, sanitize_folder_name


logger = logging.getLogger(__name__)

TAG_RULES = {
    "Projects": ["project", "build", "startup", "task"],
    "Areas": ["health", "finance", "personal", "life"],
    "Resources": ["learning", "article", "guide", "reference"],
    "Archives": ["archive", "archived", "completed", "done"],
}


@dataclass(slots=True)
class ClassificationResult:
    section: str
    folder: str
    create_folder: bool
    tags: list[str]
    source: str
    used_llm: bool
    reason: str


def _first_value(metadata: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            if value:
                candidate = str(value[0]).strip()
                if candidate:
                    return candidate
        else:
            candidate = str(value).strip()
            if candidate:
                return candidate
    return None


def _has_truthy_flag(metadata: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, bool) and value:
            return True
        if isinstance(value, str) and value.strip().lower() in {"true", "yes", "1"}:
            return True
    return False


def _section_from_tag_rules(tags: list[str]) -> str | None:
    if not tags:
        return None

    normalized = [str(tag).strip().lower() for tag in tags if str(tag).strip()]
    for section, keywords in TAG_RULES.items():
        for tag in normalized:
            for keyword in keywords:
                if keyword in tag:
                    return section
    return None


def _section_from_metadata(metadata: dict[str, Any], tags: list[str]) -> str | None:
    tag_values = list(dict.fromkeys(tags + normalized_tags(metadata.get("tags"))))
    routed_from_tags = _section_from_tag_rules(tag_values)
    if routed_from_tags:
        return routed_from_tags

    explicit = normalize_section(
        _first_value(metadata, "section", "para", "pillar", "bucket", "folder_section")
    )
    if explicit:
        return explicit

    status = str(metadata.get("status", "")).strip().lower()
    if status in ARCHIVE_STATUSES or _has_truthy_flag(metadata, "archived", "is_archived"):
        return "Archives"

    note_type = str(metadata.get("type", "")).strip().lower()
    if note_type in PROJECT_TYPES:
        return "Projects"
    if note_type in AREA_TYPES:
        return "Areas"
    if note_type in RESOURCE_TYPES:
        return "Resources"

    if _first_value(metadata, "project", "initiative", "client", "milestone"):
        return "Projects"
    if _first_value(metadata, "area", "domain", "responsibility", "owner"):
        return "Areas"
    if _first_value(metadata, "resource", "topic", "subject", "source", "reference", "category"):
        return "Resources"

    tag_value_set = set(tag_values)
    if tag_value_set & {"project", "projects"}:
        return "Projects"
    if tag_value_set & {"area", "areas"}:
        return "Areas"
    if tag_value_set & {"resource", "resources", "reference"}:
        return "Resources"
    if tag_value_set & {"archive", "archived"}:
        return "Archives"
    return None


def _folder_from_metadata(section: str, metadata: dict[str, Any], note: NoteDocument) -> str | None:
    if section == "Projects":
        return _first_value(
            metadata,
            "project",
            "initiative",
            "client",
            "milestone",
            "workstream",
        )
    if section == "Areas":
        return _first_value(metadata, "area", "domain", "responsibility", "owner")
    if section == "Resources":
        return _first_value(
            metadata,
            "resource",
            "topic",
            "subject",
            "category",
            "reference",
            "source",
        )
    if section == "Archives":
        return _first_value(
            metadata,
            "archive_bucket",
            "project",
            "area",
            "topic",
            "category",
        )
    return note.title


def _metadata_route(note: NoteDocument) -> ClassificationResult | None:
    metadata = note.frontmatter
    if not note.has_frontmatter:
        return None

    if note.has_frontmatter and not note.frontmatter_valid:
        logger.warning(
            "Invalid YAML frontmatter for %s: %s",
            note.path,
            "; ".join(note.frontmatter_errors) or "unknown validation error",
        )
        return ClassificationResult(
            section="Resources",
            folder=default_unsorted_folder(),
            create_folder=True,
            tags=note.tags,
            source="validation",
            used_llm=False,
            reason="invalid yaml fallback",
        )

    if not metadata:
        return ClassificationResult(
            section="Resources",
            folder=default_unsorted_folder(),
            create_folder=True,
            tags=note.tags,
            source="metadata",
            used_llm=False,
            reason="valid yaml with deterministic fallback",
        )

    yaml_tags = normalized_tags(metadata.get("tags"))
    tag_section = _section_from_tag_rules(yaml_tags)
    if tag_section:
        folder = _folder_from_metadata(tag_section, metadata, note)
        folder_name = sanitize_folder_name(folder, default="") if folder else ""
        create_folder = bool(folder_name) and folder_creation_allowed(tag_section)
        return ClassificationResult(
            section=nearest_valid_section(tag_section),
            folder=folder_name,
            create_folder=create_folder,
            tags=note.tags,
            source="metadata",
            used_llm=False,
            reason="yaml tag route",
        )

    section = _section_from_metadata(metadata, note.tags)
    if not section:
        return ClassificationResult(
            section="Resources",
            folder=default_unsorted_folder(),
            create_folder=True,
            tags=note.tags,
            source="metadata",
            used_llm=False,
            reason="valid yaml with fallback route",
        )

    folder = _folder_from_metadata(section, metadata, note)
    if not folder:
        folder = default_unsorted_folder()

    folder_name = sanitize_folder_name(folder, default=default_unsorted_folder())
    create_folder = folder_creation_allowed(section) and folder_name != default_unsorted_folder()
    reason = "metadata route"
    if folder_name == default_unsorted_folder():
        reason = "metadata route with fallback folder"

    return ClassificationResult(
        section=nearest_valid_section(section),
        folder=folder_name,
        create_folder=create_folder,
        tags=note.tags,
        source="metadata",
        used_llm=False,
        reason=reason,
    )


def _normalize_llm_tags(note_tags: list[str], value: Any) -> list[str]:
    tags = list(note_tags)
    for item in ensure_string_list(value):
        if item not in tags:
            tags.append(item)
    return tags


def _llm_route(note: NoteDocument) -> ClassificationResult:
    payload = classify_note_fallback(note.body or note.raw_text, note.frontmatter, note.title)
    section = nearest_valid_section(normalize_section(str(payload.get("section", "")).strip()))
    folder = sanitize_folder_name(
        str(payload.get("folder", "")).strip(),
        default=default_unsorted_folder(),
    )
    requested_create = payload.get("create_folder", False)
    if not isinstance(requested_create, bool):
        requested_create = str(requested_create).strip().lower() == "true"

    create_folder = requested_create and folder_creation_allowed(section)
    if not create_folder and not folder:
        folder = default_unsorted_folder()

    return ClassificationResult(
        section=section,
        folder=folder or default_unsorted_folder(),
        create_folder=create_folder,
        tags=_normalize_llm_tags(note.tags, payload.get("tags")),
        source="llm",
        used_llm=True,
        reason="llm fallback route",
    )


def classify_note_document(note: NoteDocument) -> ClassificationResult:
    metadata_result = _metadata_route(note)
    if metadata_result is not None:
        return metadata_result

    try:
        return _llm_route(note)
    except Exception as exc:
        logger.error("LLM fallback classification failed for %s: %s", note.path, exc, exc_info=True)
        return ClassificationResult(
            section="Resources",
            folder=default_unsorted_folder(),
            create_folder=True,
            tags=note.tags,
            source="fallback",
            used_llm=False,
            reason="deterministic fallback route",
        )
