"""Telegram Bot API publishing."""

from __future__ import annotations

from pathlib import Path

import requests

from podcast_pipeline.config import Settings, console


def build_caption(title: str, track: str | None, cfg: Settings) -> str:
    """Builds the Markdown caption: optional prefix, bold '#N. Title', optional hashtags."""
    lines = []
    if cfg.telegram_caption_prefix:
        lines.append(cfg.telegram_caption_prefix)

    episode_info = f"#{track}. " if track else ""
    lines.append(f"*{episode_info}{title}*")

    if cfg.telegram_hashtags:
        lines.append(f"\n{cfg.telegram_hashtags}")
    return "\n".join(lines)


def publish_to_telegram(
    mp3_path: Path,
    title: str,
    cfg: Settings,
    track: str | None = None,
) -> bool:
    """Sends the MP3 with `sendAudio`. Returns False when unconfigured or on any failure."""
    if not cfg.telegram_enabled:
        console.print("[dim]ℹ️ Telegram credentials not set in .env — skipping Telegram publication.[/dim]")
        return False

    url = f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendAudio"
    data = {
        "chat_id": cfg.telegram_chat_id,
        "title": title,
        "performer": cfg.artist,
        "caption": build_caption(title, track, cfg),
        "parse_mode": "Markdown",
    }

    try:
        with open(mp3_path, "rb") as audio_file:
            files = {"audio": (mp3_path.name, audio_file, "audio/mpeg")}
            response = requests.post(url, data=data, files=files, timeout=120)
            result = response.json()

        if response.status_code == 200 and result.get("ok"):
            console.print(f"[green]🚀 Successfully broadcasted to Telegram (Chat: {cfg.telegram_chat_id})[/green]")
            return True
        console.print(f"[red]❌ Telegram API error: {result.get('description', 'Unknown error')}[/red]")
        return False
    except Exception as e:
        # Never echo the request URL: it contains the bot token.
        console.print(f"[red]❌ Telegram upload exception: {type(e).__name__}[/red]")
        return False
