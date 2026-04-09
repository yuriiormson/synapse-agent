from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.utils.folders import PARA_FOLDERS, existing_folders, resolve_folder


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

load_dotenv(BASE_DIR / ".env")


@dataclass(slots=True)
class Settings:
    vault_path: Path = Path(os.getenv("VAULT_PATH", str(DATA_DIR / "vault"))).expanduser()
    llm_api: str = os.getenv(
        "LLM_API", "http://127.0.0.1:8080/v1/chat/completions"
    ).strip()
    llm_model: str = os.getenv("LLM_MODEL", "local-model").strip()
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "").strip()
    telegram_allowed_user_ids: tuple[int, ...] = tuple(
        int(value.strip())
        for value in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",")
        if value.strip()
    )
    index_db_path: Path = Path(
        os.getenv("INDEX_DB_PATH", str(DATA_DIR / "index.db"))
    ).expanduser()
    voice_temp_dir: Path = Path(
        os.getenv("VOICE_TEMP_DIR", str(DATA_DIR / "voice"))
    ).expanduser()
    request_timeout_seconds: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "300"))
    search_limit: int = int(os.getenv("SEARCH_LIMIT", "5"))
    search_snippet_chars: int = int(os.getenv("SEARCH_SNIPPET_CHARS", "220"))
    ask_context_notes: int = int(os.getenv("ASK_CONTEXT_NOTES", "3"))
    ask_context_chars: int = int(os.getenv("ASK_CONTEXT_CHARS", "1200"))
    telegram_result_limit: int = int(os.getenv("TELEGRAM_RESULT_LIMIT", "5"))
    whisper_model: str = os.getenv("WHISPER_MODEL", "small").strip()
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cpu").strip()
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8").strip()
    voice_default_mode: str = os.getenv("VOICE_DEFAULT_MODE", "ask").strip().lower()
    voice_caption_fallback: bool = os.getenv("VOICE_CAPTION_FALLBACK", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    unsorted_folder_name: str = os.getenv("UNSORTED_FOLDER_NAME", "Unsorted").strip()

    @property
    def inbox_path(self) -> Path:
        return resolve_folder(self.vault_path, "inbox")

    @property
    def inbox_paths(self) -> tuple[Path, ...]:
        existing = existing_folders(self.vault_path, "inbox")
        return existing or (self.inbox_path,)

    def ensure_directories(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.index_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.voice_temp_dir.mkdir(parents=True, exist_ok=True)
        self.vault_path.mkdir(parents=True, exist_ok=True)
        for key in PARA_FOLDERS:
            resolve_folder(self.vault_path, key)


SETTINGS = Settings()
