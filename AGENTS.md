# AGENTS.md

Entry point for AI coding agents working on this repo. Humans: see [README.md](README.md).

## What this is
A CLI that turns `.txt` scripts into tagged MP3 podcast episodes (edge-tts), then optionally posts them to Telegram.

## Commands
```bash
pip install -r requirements.txt pytest ruff   # setup (use a venv)
python pipeline.py run-all --no-tg            # process every script in Podcasts/Script/
python pipeline.py run "examples/The Sound of Rain.txt" --no-tg --no-move
python pipeline.py list-voices --filter uk
ruff check . && ruff format .                 # lint + format (line length 120)
pytest                                        # offline tests, no network needed
```

## Architecture (`podcast_pipeline/`)
| Module | Responsibility |
|---|---|
| `config.py` | `Settings` frozen dataclass built from `.env` (`Settings.from_env()`), shared rich `console` |
| `episodes.py` | Filename parsing, auto-numbering, inbox listing, archiving to `Done/` |
| `tts.py` | Native `edge-tts` streaming synthesis with live progress; `list_voices` |
| `tagging.py` | ID3v2 tags via mutagen |
| `telegram.py` | Caption building and Bot API `sendAudio` |
| `workflow.py` | `process_file`, `process_all_new`, `watch_folder` orchestration |
| `cli.py` | argparse CLI; `pipeline.py` at the root is a thin shim |

Flow: `resolve_episode` → `synthesize_speech` → `tag_audio` → `publish_to_telegram` → `archive_script`.

## Conventions
- Pass `Settings` explicitly; never read `os.environ` outside `config.py`.
- Functions return `bool` for success and print user-facing errors via `console`; they don't raise for expected failures.
- Keep tests offline: no network calls, no real MP3 synthesis.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).

## Hard rules
- **Never commit** `.env`, `Podcasts/Script/*`, `Podcasts/Audio/*`. They are git-ignored; keep it that way.
- Never print or log the Telegram bot token or any URL containing it.
- Don't change episode numbering semantics (highest number in `Podcasts/Audio/` + 1) without updating tests and README.
