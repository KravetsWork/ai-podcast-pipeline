"""Runtime configuration, loaded from environment variables / `.env`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

console = Console()

_TRUE = ("true", "1", "yes")


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in _TRUE


@dataclass(frozen=True)
class Settings:
    """All user-tunable preferences (see `.env.example`)."""

    # Speech synthesis
    tts_voice: str = "en-US-AndrewMultilingualNeural"
    tts_rate: str = "+0%"
    tts_pitch: str = "+0Hz"
    tts_volume: str = "+0%"
    max_jobs: int = 4

    # ID3 defaults
    artist: str = "AI"
    album_artist: str = "AI"
    album: str = "AI Podcasts"
    genre: str = "Podcast"

    # Folders
    script_dir: Path = Path("Podcasts/Script")
    audio_dir: Path = Path("Podcasts/Audio")
    done_dir: Path = Path("Podcasts/Script/Done")
    move_to_done: bool = True

    # Telegram (optional)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_caption_prefix: str = "🎙 *New podcast episode*"
    telegram_hashtags: str = "#podcast #AI"

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @classmethod
    def from_env(cls) -> Settings:
        """Reads `.env` (if present) and builds settings, falling back to defaults."""
        load_dotenv()
        d = cls()
        env = os.getenv
        return cls(
            tts_voice=env("TTS_VOICE", d.tts_voice),
            tts_rate=env("TTS_RATE", d.tts_rate),
            tts_pitch=env("TTS_PITCH", d.tts_pitch),
            tts_volume=env("TTS_VOLUME", d.tts_volume),
            max_jobs=max(1, int(env("MAX_JOBS", str(d.max_jobs)))),
            artist=env("DEFAULT_ARTIST", d.artist),
            album_artist=env("DEFAULT_ALBUM_ARTIST", d.album_artist),
            album=env("DEFAULT_ALBUM", d.album),
            genre=env("DEFAULT_GENRE", d.genre),
            script_dir=Path(env("SCRIPT_DIR", str(d.script_dir))),
            audio_dir=Path(env("AUDIO_DIR", str(d.audio_dir))),
            done_dir=Path(env("DONE_DIR", str(d.done_dir))),
            move_to_done=_flag("MOVE_TO_DONE", "true"),
            telegram_bot_token=env("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=env("TELEGRAM_CHAT_ID", "").strip(),
            telegram_caption_prefix=env("TELEGRAM_CAPTION_PREFIX", d.telegram_caption_prefix).strip(),
            telegram_hashtags=env("TELEGRAM_INCLUDE_HASHTAGS", d.telegram_hashtags).strip(),
        )
