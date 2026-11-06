# AI Podcast Pipeline

Turn text scripts into tagged MP3 podcast episodes and (optionally) publish them to Telegram.

```
Podcasts/Script/*.txt ──► edge-tts ──► mutagen (ID3) ──► Podcasts/Audio/*.mp3 ──► Telegram Bot API
```

- **TTS**: [edge-tts](https://github.com/rany2/edge-tts), neural voices, no API cost
- **Tagging**: [mutagen](https://mutagen.readthedocs.io), sets Title, Artist, Album Artist, Track, Album, Genre and optional cover art
- **Publishing**: Telegram Bot API `sendAudio` (optional)
- **UX**: [rich](https://github.com/Textualize/rich) console output

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # Linux/macOS: cp .env.example .env
```

Put scripts in `Podcasts/Script/`. Name them simply `Episode title.txt`: the episode number is assigned automatically as the highest number in `Podcasts/Audio/` + 1, and the MP3 becomes `N. Episode title.mp3` (the script is archived under the same name). A manual prefix such as `5. Episode title.txt` is still respected.

```bash
python pipeline.py run-all                          # process all new scripts (per-chunk debug log on by default)
python pipeline.py run "Podcasts/Script/1. Title.txt" --no-tg
python pipeline.py run-all --concurrency 2          # override parallel TTS worker count
python pipeline.py watch                            # process files as they appear
python pipeline.py list-voices --filter uk
```

## Workflow

1. Drop a new script into `Podcasts/Script/`.
2. `run-all` (or `watch`) processes only the scripts currently in that folder: synthesize, tag, send to Telegram.
3. On success the script (and its optional same-name cover `.jpg`/`.png`) is moved to `Podcasts/Script/Done/`, so the next run sees only new scripts. If the Telegram upload fails, the script stays in place and is retried on the next run.

Archiving is controlled by `MOVE_TO_DONE` / `DONE_DIR` in `.env`, or per run with `--move` / `--no-move`.
`watch` waits until a file has finished being written, ignores `Done/`, and re-processes a script if you edit it.

## Configuration

All preferences are set in `.env` (copy [.env.example](.env.example), which is preconfigured with a Ukrainian voice): voice, rate, pitch, parallel synthesis settings (`TTS_CONCURRENCY` / `TTS_RETRIES` / `TTS_DEBUG`), ID3 defaults, folders, Telegram caption/hashtags,
and optional `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`. Without Telegram credentials the pipeline only generates and tags audio locally.

## Privacy

`Podcasts/Script/*`, `Podcasts/Audio/*`, `.env` and cover assets are git-ignored. Only the code is published.

## License

[MIT](LICENSE)
