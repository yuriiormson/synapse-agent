from __future__ import annotations

from pathlib import Path


PARA_FOLDERS = {
    "inbox": ["Inbox", "0. Inbox"],
    "projects": ["Projects", "1. Projects"],
    "areas": ["Areas", "2. Areas"],
    "resources": ["Resources", "3. Resources"],
    "archives": ["Archives", "4. Archives"],
}

SECTION_FOLDER_KEYS = {
    "Projects": "projects",
    "Areas": "areas",
    "Resources": "resources",
    "Archives": "archives",
}


def resolve_folder(base_path: str | Path, key: str) -> Path:
    base = Path(base_path).expanduser()
    candidates = PARA_FOLDERS.get(str(key).strip().lower(), [])
    if not candidates:
        raise ValueError(f"Unknown PARA folder key: {key}")

    for name in candidates:
        path = base / name
        if path.exists():
            return path

    path = base / candidates[0]
    path.mkdir(parents=True, exist_ok=True)
    return path


def existing_folders(base_path: str | Path, key: str) -> tuple[Path, ...]:
    base = Path(base_path).expanduser()
    candidates = PARA_FOLDERS.get(str(key).strip().lower(), [])
    return tuple((base / name) for name in candidates if (base / name).exists())


def folder_key_for_section(section: str) -> str:
    return SECTION_FOLDER_KEYS.get(section, "resources")


def resolve_section_folder(base_path: str | Path, section: str) -> Path:
    return resolve_folder(base_path, folder_key_for_section(section))
