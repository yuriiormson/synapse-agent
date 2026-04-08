# VaultMind

Works fully offline (local LLM + local speech-to-text).
No cloud services required.

VaultMind is a deterministic local second-brain assistant for a PARA-style Obsidian vault. It runs as one small Python service, keeps your notes on disk, gives you a Telegram interface for retrieval and sorting, supports local voice transcription, and only uses a local LLM when plain metadata is not enough or when `/ask` needs a grounded summary.

It is positioned as a lightweight alternative to cloud note copilots and agent-heavy automation stacks. VaultMind does not depend on `n8n`, LangChain, vector databases, or recursive planning loops. If you use `n8n`, it can feed notes into the vault as an optional external input, nothing more.

## Why VaultMind

- Local-first: notes stay in your vault on disk
- Deterministic: file moves and routing follow explicit PARA rules
- Minimal: one Python runtime, one SQLite index, optional local LLM
- Practical: Telegram works for search, opening notes, sorting, and voice input
- GitHub-safe: the repo ships without personal vault content or machine-specific data

## Positioning

VaultMind is for people who want a local knowledge assistant, not an autonomous agent platform.

- Use VaultMind when you want deterministic note organization and retrieval
- Use VaultMind when your vault already follows PARA or something close to it
- Use VaultMind when you want voice input and Telegram access without handing your notes to a hosted SaaS
- Do not expect long-running agents, recursive planning, or hidden automation loops

## Architecture

```text
Telegram Bot (UI)
        |
        v
Python Application (single runtime)
        |
        +--> Sorter (YAML-first PARA routing)
        +--> Search + SQLite index
        +--> Voice transcription (local Whisper-compatible model)
        +--> Local LLM fallback (classification or grounded answer generation)
        |
        v
Local Vault on Disk
        |
        +--> Optional Dropbox sync through rclone or another local sync tool
        +--> Optional external note ingestion from tools like n8n
```

## Quick Start

### Local Python

1. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

2. Create a demo vault you can safely modify:

```bash
cp -R examples/vault data/vault
cp .env.example .env
```

3. Start a local OpenAI-compatible LLM endpoint if you want LLM fallback and `/ask` summaries:

```bash
python3 -m llama_cpp.server --model models/qwen.gguf --port 8080
```

4. Start VaultMind:

```bash
python3 -m app.main
```

### Docker

1. Prepare demo data:

```bash
cp -R examples/vault data/vault
cp .env.example .env
```

2. Start the app:

```bash
docker compose up --build
```

3. If you also want the bundled optional `llama.cpp` container, run:

```bash
export LLM_API=http://llama:8080/v1/chat/completions
docker compose --profile llm up --build
```

## Demo

The repo includes safe sample notes under `examples/vault/`.

Suggested demo flow:

1. Copy the sample vault to `data/vault`
2. Send `/search roadmap`
3. Send `/ask what matters for release`
4. Send `/open 1`
5. Drop a markdown note into `data/vault/Inbox/`
6. Send `/sort`
7. Send a voice message that starts with `search ...` or `ask ...`

## Features

- Telegram commands: `/search`, `/ask`, `/open`, `/sort`
- Ranked local search with snippet previews
- YAML-first Inbox routing into `Projects`, `Areas`, `Resources`, and `Archives`
- Safe fallback behavior for empty or invalid frontmatter
- Automatic folder creation only when rules allow it
- Local voice transcription with Whisper-compatible models
- Optional grounded summaries for `/ask`

## Vault Structure

VaultMind expects a PARA-style vault:

```text
Vault/
├── Inbox/
├── Projects/
├── Areas/
├── Resources/
└── Archives/
```

`Inbox` is temporary intake only. The sorter also tolerates a legacy `0. Inbox` path so older vaults still work.

## Sorting Logic

Routing is YAML-first and deterministic:

1. Parse YAML frontmatter
2. Validate known metadata fields safely
3. Use values such as `type`, `project`, `area`, `resource`, `status`, `section`, and `tags`
4. Route directly when metadata is sufficient
5. If frontmatter is invalid, fall back safely to `Resources/Unsorted`
6. If no frontmatter exists, allow at most one LLM classification call for the file
7. If that LLM step fails, fall back deterministically to `Resources/Unsorted`

This keeps LLM usage minimal while preventing notes from getting lost.

## LLM Policy

The local LLM is used only for:

- one fallback classification call per file when frontmatter is absent
- optional grounded summaries for `/ask`
- optional future structured extraction extensions

The local LLM is not used for:

- search retrieval
- routing when valid YAML exists
- recursive planning
- agent loops
- vector embeddings

## Search

Search is local and ranked. It does not depend on the LLM.

Ranking weights consider:

- exact and partial title matches
- keyword matches in note bodies
- tag matches
- folder relevance
- PARA section relevance
- frontmatter-derived metadata text
- recency from file modification time

Each result includes:

- title
- vault path
- location
- weighted score
- snippet preview
- top tags when available

## Telegram UX

- `/search <query>` returns ranked matches with previews
- `/ask <query>` runs retrieval first, then optionally summarizes from retrieved notes
- `/open <n>` returns the full note with safe output limits for Telegram
- `/sort` processes Inbox immediately and shows a concise move summary

VaultMind also keeps the latest result set per Telegram user so `/open` stays deterministic.

## Voice Support

Voice messages are handled locally:

```text
Telegram voice/audio
  -> file download
  -> local Whisper-compatible transcription
  -> /search or /ask flow
```

Voice fallback handling:

- If the transcript starts with `search ...`, VaultMind runs search mode
- If the transcript starts with `ask ...`, VaultMind runs ask mode
- Otherwise it defaults to ask mode
- If transcription fails and the message has a caption, VaultMind can use that caption as a fallback query
- If transcription fails and there is no fallback text, the bot responds with a clear recovery hint

## Environment

Copy `.env.example` to `.env` and adjust as needed:

```bash
VAULT_PATH=./data/vault
LLM_API=http://localhost:8080/v1/chat/completions
LLM_MODEL=local-model
TELEGRAM_TOKEN=
TELEGRAM_ALLOWED_USER_IDS=
INDEX_DB_PATH=./data/index.db
REQUEST_TIMEOUT_SECONDS=30
LLM_MAX_TOKENS=300
SEARCH_LIMIT=5
SEARCH_SNIPPET_CHARS=220
ASK_CONTEXT_NOTES=3
ASK_CONTEXT_CHARS=1200
TELEGRAM_RESULT_LIMIT=5
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
VOICE_DEFAULT_MODE=ask
VOICE_TEMP_DIR=./data/voice
VOICE_CAPTION_FALLBACK=true
UNSORTED_FOLDER_NAME=Unsorted
```

## Docker Files

- `Dockerfile` builds the standalone Python service
- `docker-compose.yml` runs the app and optionally an `llama.cpp` server
- `.dockerignore` keeps local data, caches, and models out of the build context

## Example Notes

The sample vault includes generic notes only. No personal, private, or machine-specific data is committed.

- Inbox notes show metadata-first sorting
- Project and resource notes support search demos
- All sample content is safe placeholder content for public release

## Scheduled Sorting

If you prefer cron for background sorting:

```bash
*/5 * * * * cd /path/to/VaultMind && python3 -m app.sorter.sorter
```

## Repo Hygiene

- No personal vault is included
- No local virtual environment is included
- No user-specific paths are committed
- No local Dropbox contents are committed
- `n8n` is optional and external, not a runtime dependency

## Repository Layout

```text
app/
├── main.py
├── config.py
├── bot/
│   └── telegram_bot.py
├── sorter/
│   ├── sorter.py
│   ├── classifier.py
│   └── rules.py
├── search/
│   ├── search.py
│   └── ranking.py
├── llm/
│   └── client.py
├── voice/
│   └── transcribe.py
└── utils/
    └── file_utils.py

data/
└── index.db

examples/
└── vault/
```
