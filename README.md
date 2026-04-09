# Synapse Agent

A local-first "second brain" that organizes your notes, lets you search them via Telegram, and works fully offline.

- 🧠 Automatic PARA organization
- 🔍 Fast local search (no vector DB)
- 🎤 Voice-to-search (Whisper)
- 🤖 Optional LLM summaries
- ⚡ Minimal dependencies, high speed

---

## Demo

1. Send a note -> goes to Inbox
2. Run `/sort` -> auto-organized
3. `/search ai` -> finds notes
4. Send voice -> transcribed -> searched

---

## First Run (Minimal Setup)

```bash
git clone <repo>
cd synapse-agent

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install faster-whisper

mkdir -p data/vault data/voice
cp .env.example .env
```

---

## Telegram Setup

1. Open Telegram -> `@BotFather`
2. Run `/newbot`
3. Copy token

Add to `.env`:

```bash
TELEGRAM_TOKEN=your_token
TELEGRAM_ALLOWED_USER_IDS=your_user_id
```

---

## Run

```bash
python -m app.main
```

---

## Commands

- `/search <query>` — find notes
- `/ask <query>` — search + summary
- `/open <n>` — open result
- `/sort` — organize inbox

---

## Voice Search

- Send voice message
- Transcribed locally (Whisper)
- Routed to search or ask

---

## How It Works

- Notes = Markdown files
- Search = local ranking (no embeddings)
- Sort = metadata-based PARA
- Voice = Whisper -> text -> search
- LLM = optional, fallback-safe

---

## Configuration

```bash
VAULT_PATH=./data/vault
LLM_API=http://localhost:8080/v1/chat/completions
LLM_MODEL=local-model

# language
AUTO_LANGUAGE=true
LLM_LANGUAGES=en,uk
```

---

## Adding Notes

- Drop `.md` into `data/vault/Inbox/`
- Send text via Telegram
- Send voice

Then:

```bash
/sort
```

---

## Troubleshooting

### Bot not responding

- Check `TELEGRAM_TOKEN`
- Check `TELEGRAM_ALLOWED_USER_IDS`

### No search results

- Ensure notes exist
- Run `/sort`

### Voice not working

- Check `WHISPER_MODEL`
- Check `data/voice` folder

### LLM not working

- Check `LLM_API` endpoint
- Check model running

---

## Limitations

- No vector semantic search
- Whisper accuracy varies by language
- LLM optional

---

## Who Is This For

- Obsidian users (PARA)
- Developers
- Local-first enthusiasts

---

## Philosophy

No agents.
No vector DB.
Just files, logic, and control.
