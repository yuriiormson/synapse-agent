from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import shutil

from app.config import SETTINGS
from app.search.search import refresh_index
from app.sorter.classifier import ClassificationResult, classify_note_document
from app.sorter.rules import default_unsorted_folder, folder_creation_allowed
from app.utils.file_utils import NoteDocument, build_destination_path, read_note, relative_to_base
from app.utils.folders import resolve_section_folder


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SortResult:
    source_path: Path
    destination_path: Path
    classification: ClassificationResult


def _resolve_target_dir(classification: ClassificationResult) -> Path:
    section_dir = resolve_section_folder(SETTINGS.vault_path, classification.section)
    target_dir = section_dir / classification.folder

    if target_dir.exists():
        return target_dir

    if classification.create_folder and folder_creation_allowed(classification.section):
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    if classification.folder == default_unsorted_folder():
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    return section_dir


def process_file(file_path: str | Path) -> SortResult:
    path = Path(file_path)
    try:
        note = read_note(path)
        classification = classify_note_document(note)
        target_dir = _resolve_target_dir(classification)
        destination_path = build_destination_path(target_dir, path.name)
        shutil.move(path.as_posix(), destination_path.as_posix())
    except (RuntimeError, OSError) as exc:
        logger.error("Failed to sort file %s: %s", path, exc, exc_info=True)
        raise RuntimeError(f"Failed to sort file: {path}") from exc

    logger.info(
        "Sorted %s -> %s [%s]",
        relative_to_base(path, SETTINGS.vault_path),
        relative_to_base(destination_path, SETTINGS.vault_path),
        classification.source,
    )
    return SortResult(
        source_path=path,
        destination_path=destination_path,
        classification=classification,
    )


def _iter_inbox_notes() -> list[Path]:
    inbox_notes: list[Path] = []
    seen_paths: set[Path] = set()
    for inbox_path in SETTINGS.inbox_paths:
        if not inbox_path.exists():
            continue
        for note_path in sorted(inbox_path.glob("*.md")):
            if note_path.is_file() and note_path not in seen_paths:
                inbox_notes.append(note_path)
                seen_paths.add(note_path)
    return inbox_notes


def run() -> list[SortResult]:
    SETTINGS.ensure_directories()

    results: list[SortResult] = []
    for path in _iter_inbox_notes():
        try:
            results.append(process_file(path))
        except RuntimeError:
            continue

    refresh_index(SETTINGS.vault_path)
    return results


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    results = run()
    for item in results:
        source = relative_to_base(item.source_path, SETTINGS.vault_path)
        destination = relative_to_base(item.destination_path, SETTINGS.vault_path)
        print(f"{source} -> {destination} [{item.classification.source}]")
    print(f"Processed {len(results)} markdown file(s).")


if __name__ == "__main__":
    main()
