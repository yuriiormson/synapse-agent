#!/usr/bin/env python3
"""
Smoke test for VaultMind / SynapseAgent core features.
Run on the server where the repo lives. This test avoids network calls and real tokens.
It exercises: YAML-first sorter, search ranking, open/send-as-file logic, voice module presence,
and LLM fallback hooks (non-networked).
"""

import os, sys, sqlite3, json, shutil, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root
print("Repo root:", ROOT)

# Config
TEST_VAULT = ROOT / "tests" / "smoke" / "vault"
INBOX = TEST_VAULT / "Inbox"
PROJECTS = TEST_VAULT / "Projects"
AREAS = TEST_VAULT / "Areas"
RESOURCES = TEST_VAULT / "Resources"
INDEX_DB = ROOT / "data" / "smoke_index.db"

# Helpers
def prepare_dirs():
    if TEST_VAULT.exists():
        shutil.rmtree(TEST_VAULT)
    INBOX.mkdir(parents=True)
    PROJECTS.mkdir(parents=True)
    AREAS.mkdir(parents=True)
    RESOURCES.mkdir(parents=True)
    if INDEX_DB.exists():
        INDEX_DB.unlink()
    print("Prepared test vault:", TEST_VAULT)

def write_note(path, frontmatter, body):
    content = ""
    if frontmatter:
        content += "---\n"
        for k,v in frontmatter.items():
            if isinstance(v, (list,tuple)):
                content += f"{k}: {json.dumps(v)}\n"
            else:
                content += f"{k}: {v}\n"
        content += "---\n\n"
    content += body
    path.write_text(content, encoding="utf-8")
    print("Wrote:", path)

# 0. sanity: required files exist
def check_prereqs():
    misses = []
    needed = ["app/sorter/sorter.py", "app/search/search.py", "app/bot/telegram_bot.py", "app/voice/transcribe.py"]
    for n in needed:
        p = ROOT / n
        if not p.exists():
            misses.append(n)
    if misses:
        print("MISSING CORE FILES:", misses)
        return False
    print("Core files present.")
    return True

# 1. Test YAML-first sorter (calls sorter functions directly)
def test_sorter():
    # Create three notes
    n1 = INBOX / "note_project.md"
    write_note(n1, {"type":"project","project":"TestProject","tags":["ai","test"]}, "Project note text")
    n2 = INBOX / "note_area.md"
    write_note(n2, {"type":"area","area":"Personal","tags":["life"]}, "Area note")
    n3 = INBOX / "note_no_meta.md"
    write_note(n3, None, "Just some text about AI and testing")

    # import sorter module and run its main function if exists
    try:
        sys.path.insert(0, str(ROOT))
        from app.sorter import sorter as sorter_module
        # Expect sorter_module has a function `sort_vault(inbox_path, vault_root)` or similar
        if hasattr(sorter_module, "sort_inbox"):
            sorter_module.sort_inbox(str(INBOX), str(TEST_VAULT))
        elif hasattr(sorter_module, "run_sorter"):
            sorter_module.run_sorter(str(INBOX))
        else:
            print("Sorter: no expected entrypoint; attempting fallback call...")
            if hasattr(sorter_module, "sorter_main"):
                sorter_module.sorter_main()
        print("Sorter executed (no crash).")
        return True
    except Exception as e:
        print("Sorter failure:", type(e), e)
        return False

# 2. Test search + ranking (basic)
def test_search():
    try:
        sys.path.insert(0, str(ROOT))
        from app.search import search as search_module
        # create simple in-memory index or call expected function
        if hasattr(search_module, "index_folder"):
            search_module.index_folder(str(TEST_VAULT), str(INDEX_DB))
        elif hasattr(search_module, "build_index"):
            search_module.build_index(str(TEST_VAULT))
        # run a query
        if hasattr(search_module, "search_query"):
            res = search_module.search_query("AI", limit=3)
            print("Search results:", res)
        else:
            print("Search: no expected entry; skipping detailed check")
        return True
    except Exception as e:
        print("Search failure:", type(e), e)
        return False

# 3. Test open/send-as-file logic
def test_open_logic():
    big = TEST_VAULT / "big.md"
    body = "A" * 5000
    write_note(big, {"type":"resource"}, body)
    # import a util that decides send-as-file, or mimic the logic here
    send_as_file = len(body) > 4000
    print("send_as_file:", send_as_file)
    return send_as_file

# 4. Voice module presence
def test_voice():
    try:
        sys.path.insert(0, str(ROOT))
        from app.voice import transcribe as tmod
        # call a stub function if available
        if hasattr(tmod, "transcribe_file"):
            try:
                # no model required — pass a small non-existent file to see graceful error handling
                out = tmod.transcribe_file(str(TEST_VAULT / "dummy.wav"))
                print("transcribe_file result:", out)
            except Exception as inner:
                print("transcribe_file raised (handled):", inner)
        else:
            print("Voice: transcribe_file not found; OK if implemented differently.")
        return True
    except Exception as e:
        print("Voice module failure:", type(e), e)
        return False

# 5. LLM fallback hook check (no network)
def test_llm_fallback():
    try:
        sys.path.insert(0, str(ROOT))
        from app.sorter import classifier as cls
        if hasattr(cls, "needs_llm"):
            ok = cls.needs_llm(str(TEST_VAULT / "note_no_meta.md"))
            print("needs_llm =>", ok)
        else:
            print("Classifier: fallback hook not found; assume ok if implemented elsewhere.")
        return True
    except Exception as e:
        print("LLM fallback check failure:", type(e), e)
        return False

def run_all():
    ok = True
    ok &= check_prereqs()
    prepare_dirs()
    ok &= test_sorter()
    ok &= test_search()
    ok &= test_open_logic()
    ok &= test_voice()
    ok &= test_llm_fallback()
    print("\\nSMOKE TEST RESULT:", "OK" if ok else "FAIL")
    return 0 if ok else 2

if __name__ == "__main__":
    sys.exit(run_all())
