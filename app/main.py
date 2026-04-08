from __future__ import annotations

import logging

from app.bot.telegram_bot import run_bot
from app.config import SETTINGS
from app.search.search import initialize_index, refresh_index


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    SETTINGS.ensure_directories()
    initialize_index()
    refresh_index(SETTINGS.vault_path)
    run_bot()


if __name__ == "__main__":
    main()
