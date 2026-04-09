from __future__ import annotations

import asyncio
from io import BytesIO
import logging
from pathlib import Path
import re

from telegram import InputFile, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import SETTINGS
from app.handlers.inbox import save_to_inbox
from app.llm.client import answer_query
from app.search.ranking import SearchResult
from app.search.search import load_user_session, save_user_session, search
from app.sorter.sorter import run as run_sorter
from app.utils.file_utils import chunk_text, extract_title, read_note, relative_to_base
from app.voice.transcribe import transcribe_audio


logger = logging.getLogger(__name__)
user_sessions: dict[int, list[SearchResult]] = {}
TELEGRAM_MESSAGE_LIMIT = 4000
VOICE_TRANSCRIPTION_TIMEOUT_SECONDS = 180


def _result_fetch_limit() -> int:
    return max(SETTINGS.search_limit, SETTINGS.telegram_result_limit)


def _log_user_action(update: Update, command: str) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    logging.info(f"User {user_id} executed command: {command}")


def _is_allowed(user_id: int | None) -> bool:
    if user_id is None:
        return False
    if not SETTINGS.telegram_allowed_user_ids:
        return True
    return user_id in SETTINGS.telegram_allowed_user_ids


async def _reply(update: Update, text: str) -> None:
    if not update.effective_message:
        return
    try:
        await update.effective_message.reply_text(text)
    except Exception as exc:  # pragma: no cover - runtime protection
        logger.error("Telegram reply failed: %s", exc, exc_info=True)


async def _reply_long(update: Update, text: str) -> None:
    for chunk in chunk_text(text):
        await _reply(update, chunk)


async def _guard(update: Update) -> bool:
    if _is_allowed(update.effective_user.id if update.effective_user else None):
        return True
    await _reply(update, "Access denied.")
    return False


def _remember_results(user_id: int | None, results: list[SearchResult]) -> None:
    if user_id is None:
        return
    user_sessions[user_id] = results
    try:
        save_user_session(user_id, results)
    except Exception:
        logger.error("Failed to persist session for user %s.", user_id, exc_info=True)


def _get_recent_results(user_id: int | None) -> list[SearchResult]:
    if user_id is None:
        return []
    cached = user_sessions.get(user_id, [])
    if cached:
        return cached
    try:
        restored = load_user_session(user_id, SETTINGS.vault_path)
    except Exception:
        logger.error("Failed to load persisted session for user %s.", user_id, exc_info=True)
        return []
    if restored:
        user_sessions[user_id] = restored
    return restored


def _safe_filename(name: str, suffix: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    return f"{cleaned or 'vaultmind'}{suffix}"


async def _reply_file(
    update: Update,
    text: str,
    filename: str,
    *,
    caption: str | None = None,
) -> None:
    if not update.effective_message:
        return

    buffer = BytesIO(text.encode("utf-8"))
    buffer.seek(0)
    try:
        await update.effective_message.reply_document(
            document=InputFile(buffer, filename=filename),
            caption=caption,
        )
    except Exception as exc:  # pragma: no cover - runtime protection
        logger.error("Telegram file reply failed: %s", exc, exc_info=True)
        await _reply(update, caption or f"Response was too large to send as {filename}.")


async def _reply_text_or_file(
    update: Update,
    text: str,
    *,
    filename: str,
    caption: str | None = None,
) -> None:
    if len(text) > TELEGRAM_MESSAGE_LIMIT:
        await _reply_file(update, text, filename, caption=caption)
        return
    await _reply(update, text)


def _highlight_query(snippet: str, query: str) -> str:
    if not snippet or not query.strip():
        return snippet
    pattern = re.compile(re.escape(query.strip()), re.IGNORECASE)
    return pattern.sub(lambda match: f"*{match.group(0)}*", snippet)


def _render_search_results(results: list[SearchResult], query: str) -> str:
    if not results:
        return "No notes found. Try different keywords."

    limited_results = results[: SETTINGS.telegram_result_limit]
    lines: list[str] = [f"🔍 Found {len(results)} notes:", ""]
    for index, item in enumerate(limited_results, start=1):
        display_title = extract_title(item.relative_path)
        snippet = re.sub(r"\s+", " ", item.snippet or "").replace("\n", " ").strip()
        if len(snippet) > 120:
            snippet = f"{snippet[:117].rstrip()}..."
        snippet = _highlight_query(snippet, query)
        lines.append(f"{index}. {display_title}")
        if snippet:
            lines.append(f"   → {snippet}")
        else:
            lines.append(f"   → {item.relative_path}")
        lines.append("")
    if len(results) > len(limited_results):
        lines.append(f"Showing top {len(limited_results)} results.")
    lines.append("Use /open <number> to read a full note.")
    return "\n".join(line for line in lines if line is not None).strip()


def _render_sources(results: list[SearchResult]) -> str:
    return "\n".join(
        f"{index}. {item.title} ({item.relative_path})"
        for index, item in enumerate(results[: SETTINGS.ask_context_notes], start=1)
    )


def _build_ask_context(results: list[SearchResult]) -> list[dict[str, str]]:
    contexts: list[dict[str, str]] = []
    for item in results[: SETTINGS.ask_context_notes]:
        try:
            note = read_note(item.path)
        except RuntimeError as exc:
            logger.error("Failed to read note for ask context: %s", exc, exc_info=True)
            continue
        content = note.body[: SETTINGS.ask_context_chars].strip()
        contexts.append(
            {
                "path": item.relative_path,
                "title": item.title,
                "snippet": item.snippet,
                "content": content,
            }
        )
    return contexts


def _normalize_voice_query(transcript: str) -> tuple[str, str]:
    cleaned = transcript.strip()
    lowered = cleaned.lower()

    if lowered.startswith("/search "):
        return "search", cleaned[8:].strip()
    if lowered.startswith("search "):
        return "search", cleaned[7:].strip()
    if lowered.startswith("/ask "):
        return "ask", cleaned[5:].strip()
    if lowered.startswith("ask "):
        return "ask", cleaned[4:].strip()

    default_mode = "search" if SETTINGS.voice_default_mode == "search" else "ask"
    return default_mode, cleaned


def _caption_fallback_query(update: Update) -> tuple[str, str] | None:
    message = update.effective_message
    if not message or not SETTINGS.voice_caption_fallback:
        return None
    caption = (message.caption or "").strip()
    if not caption:
        return None
    mode, query = _normalize_voice_query(caption)
    return (mode, query) if query else None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    _log_user_action(update, "/start")
    await _reply(
        update,
        "VaultMind is ready.\n"
        "/search <query> for ranked retrieval\n"
        "/ask <query> for retrieval plus optional summary\n"
        "/open <number> to read a result\n"
        "/sort to process Inbox\n"
        "Voice messages are transcribed locally.",
    )


async def _run_search(
    update: Update,
    query: str,
    *,
    lead_text: str | None = None,
) -> list[SearchResult]:
    try:
        results = await asyncio.to_thread(search, query, SETTINGS.vault_path, _result_fetch_limit())
    except Exception as exc:  # pragma: no cover - runtime protection
        logger.error("Search failed: %s", exc, exc_info=True)
        await _reply(update, "Search failed. Check the local index and vault path.")
        return []

    logger.info(
        "Telegram /search from user %s: %s",
        update.effective_user.id if update.effective_user else None,
        query,
    )
    _remember_results(update.effective_user.id if update.effective_user else None, results)
    response = _render_search_results(results, query)
    if lead_text:
        response = f"{lead_text}\n\n{response}"
    await _reply_long(update, response)
    return results


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    _log_user_action(update, "/search")

    query = " ".join(context.args).strip()
    if not query:
        await _reply(update, "Usage: /search <query>")
        return

    await _run_search(update, query)


async def _run_ask(update: Update, query: str, *, lead_text: str | None = None) -> None:
    try:
        results = await asyncio.to_thread(search, query, SETTINGS.vault_path, _result_fetch_limit())
    except Exception as exc:  # pragma: no cover - runtime protection
        logger.error("Ask retrieval failed: %s", exc, exc_info=True)
        await _reply(update, "Retrieval failed. Check the local index and vault path.")
        return

    if not results:
        await _reply(update, "No notes found. Try different keywords.")
        return

    logger.info(
        "Telegram /ask from user %s: %s",
        update.effective_user.id if update.effective_user else None,
        query,
    )
    _remember_results(update.effective_user.id if update.effective_user else None, results)

    answer_text: str
    fallback_render = False
    try:
        contexts = await asyncio.to_thread(_build_ask_context, results)
        answer_text = await asyncio.to_thread(answer_query, query, contexts)
    except Exception as exc:  # pragma: no cover - runtime protection
        logger.error("Ask summarization failed: %s", exc, exc_info=True)
        answer_text = "LLM summary unavailable. Returning ranked note matches instead."
        fallback_render = True

    if fallback_render:
        message = (
            f"{answer_text}\n\n"
            f"{_render_search_results(results, query)}"
        )
    else:
        message = (
            f"{answer_text}\n\n"
            f"Sources:\n{_render_sources(results)}\n\n"
            "Use /open <number> to read the full note."
        )
    if lead_text:
        message = f"{lead_text}\n\n{message}"
    await _reply_text_or_file(
        update,
        message,
        filename=_safe_filename(f"ask-{query[:40]}", ".txt"),
        caption="Answer was too long for Telegram, sent as a file.",
    )


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    _log_user_action(update, "/ask")

    query = " ".join(context.args).strip()
    if not query:
        await _reply(update, "Usage: /ask <query>")
        return

    await _run_ask(update, query)


async def sort_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    _log_user_action(update, "/sort")

    try:
        results = await asyncio.to_thread(run_sorter)
    except Exception as exc:  # pragma: no cover - runtime protection
        logger.error("Sort failed: %s", exc, exc_info=True)
        await _reply(update, "Sort failed. Check the local LLM server, metadata, and vault permissions.")
        return

    if not results:
        await _reply(update, "No markdown notes found in Inbox.")
        return

    logger.info(
        "Telegram /sort from user %s processed %s notes",
        update.effective_user.id if update.effective_user else None,
        len(results),
    )
    preview = results[: SETTINGS.telegram_result_limit]
    lines = [f"Sorted {len(results)} note(s)."]
    lines.extend(
        (
            f"- {relative_to_base(item.source_path, SETTINGS.vault_path)} -> "
            f"{relative_to_base(item.destination_path, SETTINGS.vault_path)} "
            f"[{item.classification.source}]"
        )
        for item in preview
    )
    if len(results) > len(preview):
        lines.append(f"...and {len(results) - len(preview)} more.")
    await _reply_long(update, "\n".join(lines))


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    _log_user_action(update, "message")

    message = update.effective_message
    if message is None or not message.text:
        return

    text = message.text.strip()
    if not text:
        return

    try:
        saved_path = await asyncio.to_thread(save_to_inbox, SETTINGS.vault_path, text)
    except Exception as exc:  # pragma: no cover - runtime protection
        logger.error("Failed to save Telegram message to Inbox: %s", exc, exc_info=True)
        await _reply(update, "Could not save that note to Inbox.")
        return

    relative_path = relative_to_base(Path(saved_path), SETTINGS.vault_path)
    await _reply(update, f"Saved to Inbox:\n{relative_path}")


async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    _log_user_action(update, "/open")

    if not context.args or not context.args[0].isdigit():
        await _reply(update, "Invalid selection. Use /search first.")
        return

    results = _get_recent_results(update.effective_user.id if update.effective_user else None)
    if not results:
        await _reply(update, "No active search session. Use /search first.")
        return

    index = int(context.args[0]) - 1
    if index < 0 or index >= len(results):
        await _reply(update, "Invalid selection. Use /search first.")
        return

    try:
        note = read_note(results[index].path)
    except RuntimeError as exc:
        logger.error("Failed to open note: %s", exc, exc_info=True)
        await _reply(update, "Could not open that note right now.")
        return

    title = extract_title(results[index].relative_path)
    await _reply(update, f"📄 Opening: {title}\n\n")

    lines = [
        f"Path: {results[index].relative_path}",
    ]
    if results[index].tags:
        lines.append(f"Tags: {', '.join(results[index].tags[:6])}")
    lines.append("")
    lines.append(note.raw_text)
    await _reply_text_or_file(
        update,
        "\n".join(lines),
        filename=_safe_filename(title, ".md"),
        caption=f"Opened: {title}",
    )


async def _run_voice_fallback(update: Update, mode: str, query: str, reason: str) -> None:
    lead_text = f"{reason}\nFallback ({mode}): \"{query}\""
    if mode == "search":
        await _run_search(update, query, lead_text=lead_text)
        return
    await _run_ask(update, query, lead_text=lead_text)


async def voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    _log_user_action(update, "voice")

    message = update.effective_message
    if message is None:
        return

    media = message.voice or message.audio
    if media is None:
        await _reply(update, "No voice message found.")
        return

    voice_file = await media.get_file()
    suffix = Path(voice_file.file_path or "voice.ogg").suffix or ".ogg"
    target_path = SETTINGS.voice_temp_dir / f"{media.file_unique_id}{suffix}"

    try:
        await voice_file.download_to_drive(custom_path=target_path)
        logger.info(
            "Downloaded voice message for user %s to %s",
            update.effective_user.id if update.effective_user else None,
            target_path.name,
        )
        transcription = await asyncio.wait_for(
            asyncio.to_thread(transcribe_audio, target_path),
            timeout=VOICE_TRANSCRIPTION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error(
            "Voice transcription timed out for user %s.",
            update.effective_user.id if update.effective_user else None,
        )
        fallback = _caption_fallback_query(update)
        if fallback is not None:
            await _run_voice_fallback(
                update,
                fallback[0],
                fallback[1],
                "Voice transcription timed out. Using the caption instead.",
            )
        else:
            await _reply(update, "Voice transcription timed out. Try a shorter clip or send text.")
        return
    except Exception as exc:  # pragma: no cover - runtime protection
        logger.error("Voice transcription failed: %s", exc, exc_info=True)
        fallback = _caption_fallback_query(update)
        if fallback is not None:
            await _run_voice_fallback(
                update,
                fallback[0],
                fallback[1],
                "Voice transcription failed. Using the caption instead.",
            )
        else:
            await _reply(
                update,
                "Voice transcription failed. Send text or add a caption like "
                "`search project roadmap` or `ask what changed`.",
            )
        return
    finally:
        if target_path.exists():
            target_path.unlink()

    mode, query = _normalize_voice_query(transcription.text)
    if not query.strip():
        fallback = _caption_fallback_query(update)
        if fallback is not None:
            await _run_voice_fallback(
                update,
                fallback[0],
                fallback[1],
                "Voice transcription was empty. Using the caption instead.",
            )
        else:
            await _reply(update, "Could not understand audio.")
        return

    lead_text = f'Transcript ({mode}): "{query}"'
    if mode == "search":
        await _run_search(update, query, lead_text=lead_text)
        return

    await _run_ask(update, query, lead_text=lead_text)


def build_application() -> Application:
    if not SETTINGS.telegram_token:
        raise RuntimeError("TELEGRAM_TOKEN is not configured.")

    SETTINGS.ensure_directories()
    application = ApplicationBuilder().token(SETTINGS.telegram_token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sort", sort_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("ask", ask))
    application.add_handler(CommandHandler("open", open_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_message))
    return application


def run_bot() -> None:
    logger.info("Starting VaultMind Telegram bot.")
    build_application().run_polling()
