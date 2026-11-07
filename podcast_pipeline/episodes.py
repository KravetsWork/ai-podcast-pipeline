"""Episode discovery: filename parsing, numbering, archiving."""

from __future__ import annotations

import asyncio
import re
import shutil
import time
from pathlib import Path

from podcast_pipeline.config import Settings, console


def parse_filename(filepath: Path) -> tuple[str | None, str]:
    """
    Extracts an optional episode number and the clean title from a filename.

    '2. The Architecture of Emptiness.txt' -> ('2', 'The Architecture of Emptiness')
    'The Big Bang.txt'                     -> (None, 'The Big Bang')
    """
    match = re.match(r"^(\d+)[\.\s\-_]+(.*)$", filepath.stem)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return None, filepath.stem.strip()


def list_inbox_scripts(cfg: Settings) -> list[Path]:
    """Lists .txt scripts directly in the script folder (subfolders such as Done/ are ignored)."""
    return sorted(p for p in cfg.script_dir.glob("*.txt") if p.is_file())


def find_existing_mp3(script_path: Path, cfg: Settings) -> Path | None:
    """Returns the existing MP3 path for `script_path` if one is already in `audio_dir`."""
    track, title = parse_filename(script_path)
    if track:
        candidate = cfg.audio_dir / f"{script_path.stem}.mp3"
        return candidate if candidate.exists() else None

    if cfg.audio_dir.exists():
        for mp3 in cfg.audio_dir.glob("*.mp3"):
            _, t = parse_filename(mp3)
            if t == title:
                return mp3
    return None


def resolve_episode(script_path: Path, cfg: Settings) -> tuple[str | None, str, Path]:
    """
    Returns (track, title, output_mp3) for a script.

    A leading number in the filename is respected. Otherwise the number is assigned
    automatically as (highest number in the audio folder) + 1 and the MP3 is named
    '<N>. <title>.mp3'. An unnumbered script whose title already has an MP3 reuses it.
    """
    track, title = parse_filename(script_path)
    if track:
        return track, title, cfg.audio_dir / f"{script_path.stem}.mp3"

    highest = 0
    if cfg.audio_dir.exists():
        for mp3 in cfg.audio_dir.glob("*.mp3"):
            n, t = parse_filename(mp3)
            if n:
                highest = max(highest, int(n))
            if t == title:
                return n, title, mp3

    track = str(highest + 1)
    return track, title, cfg.audio_dir / f"{track}. {title}.mp3"


def archive_script(script_path: Path, cfg: Settings, new_stem: str | None = None) -> Path | None:
    """Moves a processed script into the done folder, optionally renaming it."""
    try:
        cfg.done_dir.mkdir(parents=True, exist_ok=True)
        if not script_path.is_file():
            return None
        name = f"{new_stem}{script_path.suffix}" if new_stem else script_path.name
        dest = cfg.done_dir / name
        if dest.exists():
            dest = cfg.done_dir / f"{dest.stem}.{time.strftime('%Y%m%d-%H%M%S')}{script_path.suffix}"
        shutil.move(str(script_path), str(dest))
        console.print(f"[dim]📁 Archived to {cfg.done_dir}/[/dim]")
        return dest
    except Exception as e:
        console.print(f"[red]❌ Could not archive {script_path.name}: {e}[/red]")
        return None


async def wait_until_stable(path: Path, checks: int = 2, interval: float = 1.0) -> bool:
    """Waits until the file size stops changing (the file has finished being written)."""
    last_size = -1
    stable = 0
    while stable < checks:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return False
        stable = stable + 1 if size == last_size else 0
        last_size = size
        await asyncio.sleep(interval)
    return True
