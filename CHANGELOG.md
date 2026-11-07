# Changelog

## 1.0.0
- Refactored the single-file script into the `podcast_pipeline` package (`config`, `episodes`, `tts`, `tagging`, `telegram`, `workflow`, `cli`).
- Simplified speech synthesis to use native `edge_tts.Communicate.stream()` with atomic temporary files and a live multi-file progress display.
- Added parallel file processing (`MAX_JOBS=4` / `--jobs N`) for `run-all` and `watch`, with completion-order episode numbering so episodes post to Telegram in strict sequence (`11, 12, 13, 14`).
- Automatic episode numbering, archiving to `Done/`, folder watcher, and Telegram publishing (without risking bot token leaks in error logs).
- Removed cover art embedding and `ASSETS_DIR` handling to keep the pipeline lightweight.
- Added offline unit tests, GitHub Actions CI, `AGENTS.md`, and an example script.
