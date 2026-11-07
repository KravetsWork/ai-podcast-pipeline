# 🎙️ AI Podcast Pipeline

**Drop plain-text scripts into a folder — get numbered, ID3-tagged MP3 podcast episodes delivered straight to your Telegram channel at zero API cost.**

Built for turning AI-generated deep dives (Claude, ChatGPT, Gemini), long-form essays, or study notes into a personal or public audio feed you can listen to anywhere on your phone.

```mermaid
flowchart LR
    A["Podcasts/Script/*.txt"] --> B["edge-tts<br/>(4 parallel workers)"]
    B --> C["mutagen<br/>(ID3v2 tags)"]
    C --> D["Podcasts/Audio/N. Title.mp3"]
    D --> E["Telegram Bot API<br/>(sendAudio)"]
    E --> F["Podcasts/Script/Done/"]
```

## 💡 Why This Exists

- **Zero TTS API bills:** Uses Microsoft Edge's neural Read Aloud voices via [edge-tts](https://github.com/rany2/edge-tts) — 400+ natural voices across dozens of languages with no API key required.
- **Telegram as your podcast player:** Telegram's built-in audio player reads ID3 `Title`, `Artist`, and `Track` tags, supports background playback, 1.5x/2x speed, and offline caching — no RSS hosting needed.
- **Zero manual bookkeeping:** Drop `The Architecture of Emptiness.txt` into `Podcasts/Script/`. The pipeline synthesizes up to 4 episodes in parallel, assigns the next episode number (`#11`, `#12`, `#13`...) in strict completion order, tags the MP3, posts it to Telegram, and moves the script to `Done/`.

## ✨ Features

- **Native `edge-tts` streaming** with atomic `.tmp` writes and a live multi-file `Rich` progress display (`%`, `KB`, elapsed time, ETA).
- **Parallel batch & watch modes** (`MAX_JOBS=4` / `--jobs N`) with a publish lock that guarantees episodes are numbered and posted to Telegram in exact sequential order (`11, 12, 13, 14`).
- **Complete ID3v2 metadata** via [mutagen](https://mutagen.readthedocs.io): Title, Artist, Album Artist, Album, Genre, and Track number.
- **Self-healing inbox:** Failed uploads stay in `Podcasts/Script/` for the next run; corrupt stub MP3s (`< 4 KB`) are automatically regenerated.

## 🖥️ Terminal Preview

```text
$ python pipeline.py run-all
Found 1 script(s) in Podcasts/Script/ (running up to 4 in parallel)
╭─────────────────────────────── Processing Episode ───────────────────────────────╮
│ Episode: The Sound of Rain.txt                                                   │
│ Title: The Sound of Rain                                                         │
│ Track: Auto (assigned on completion)                                             │
│ Voice: en-US-AndrewMultilingualNeural                                            │
╰──────────────────────────────────────────────────────────────────────────────────╯
⠋ The Sound of Rain.txt [1/1] ━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 228 KB • Elapsed: 0:00:08 • ETA: 0:00:00
✅ Audio generated: 1. The Sound of Rain.mp3
🏷️ ID3 metadata tagged: 1. The Sound of Rain.mp3
🚀 Successfully broadcasted to Telegram (Chat: @my_podcast_channel)
📁 Archived to Podcasts/Script/Done/

🎉 Done! Processed 1 new episode(s).
```

## 🚀 Quickstart

```bash
git clone https://github.com/KravetsWork/ai-podcast-pipeline.git
cd ai-podcast-pipeline
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # Linux/macOS: cp .env.example .env
```

Try it immediately with the bundled sample script (runs locally without Telegram and keeps the sample file in place):

```bash
python pipeline.py run "examples/The Sound of Rain.txt" --no-tg --no-move
```

The generated MP3 appears in `Podcasts/Audio/1. The Sound of Rain.mp3`.

## 🧭 Usage

| Command | What it does |
|---|---|
| `python pipeline.py run-all` | Process all new scripts in `Podcasts/Script/` (up to `MAX_JOBS` in parallel) |
| `python pipeline.py run "<file>"` | Process a single `.txt` script |
| `python pipeline.py watch` | Watch `Podcasts/Script/` and process new/modified files automatically |
| `python pipeline.py list-voices --filter uk` | List available voices (filter by locale or name, e.g. `en`, `uk`, `ru`) |

**Common flags:**
- `--jobs N` — override parallel file workers for `run-all` or `watch` (default: `MAX_JOBS=4`)
- `--no-tg` — generate and tag audio locally without sending to Telegram
- `--force` — overwrite existing audio
- `--move` / `--no-move` — archive or keep processed scripts in `Podcasts/Script/`
- `--voice <name>` / `--rate +10%` — override voice or speaking speed for a single run

## ⚙️ Configuration (`.env`)

Copy [.env.example](.env.example) to `.env` to customize settings:

| Variable | Default | Purpose |
|---|---|---|
| `TTS_VOICE` | `en-US-AndrewMultilingualNeural` | Any voice from `python pipeline.py list-voices` |
| `TTS_RATE` / `TTS_PITCH` / `TTS_VOLUME` | `+0%` / `+0Hz` / `+0%` | Prosody adjustments |
| `MAX_JOBS` | `4` | Parallel file workers in `run-all` and `watch` |
| `DEFAULT_ARTIST` / `DEFAULT_ALBUM_ARTIST` | `AI` / `AI` | ID3 Artist & Album Artist tags |
| `DEFAULT_ALBUM` / `DEFAULT_GENRE` | `AI Podcasts` / `Podcast` | ID3 Album & Genre tags |
| `SCRIPT_DIR` / `AUDIO_DIR` / `DONE_DIR` | `Podcasts/...` | Input, output, and archive directories |
| `MOVE_TO_DONE` | `true` | Move scripts to `DONE_DIR` after processing |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | *(empty)* | Leave empty for local-only MP3 generation |
| `TELEGRAM_CAPTION_PREFIX` / `TELEGRAM_INCLUDE_HASHTAGS` | `🎙 *New podcast episode*` / `"#podcast #AI"` | Telegram post caption formatting (keep hashtags quoted) |

### Telegram Setup (Optional)

1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot` → copy your `TELEGRAM_BOT_TOKEN`.
2. Add the bot as an administrator of your Telegram channel or group (with permission to post messages).
3. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (e.g. `@your_channel` or `-100xxxxxxxxxx`) in `.env`.

## 🗂️ Project Structure

```text
pipeline.py              # CLI entry point shim
podcast_pipeline/
  config.py              # Frozen Settings dataclass loaded from .env
  episodes.py            # Filename parsing, auto-numbering, inbox & archive helpers
  tts.py                 # Native edge-tts streaming with atomic writes & Rich progress
  tagging.py             # ID3v2 tagging via mutagen
  telegram.py            # Caption builder & Telegram Bot API sendAudio
  workflow.py            # Parallel batch, single-file, and folder-watcher orchestration
  cli.py                 # argparse CLI
tests/                   # Offline pytest unit suite
examples/                # Sample episode script
```

AI coding agents: see [AGENTS.md](AGENTS.md).

## 🔒 Privacy

`Podcasts/Script/*`, `Podcasts/Audio/*`, and `.env` are git-ignored so your personal scripts, generated audio, and credentials are never committed.

## 🧪 Development

```bash
pip install -r requirements.txt pytest ruff
ruff check . && pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md).

## 📄 License

[MIT](LICENSE)
