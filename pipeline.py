"""
AI Podcast Automation Pipeline
==============================
Automates:
1. Speech Synthesis (edge-tts) from text scripts.
2. ID3 Metadata Tagging (mutagen) - Title, Artist (AI), Album Artist (AI), Track, Cover Art.
3. Telegram Broadcasting (Telegram Bot API sendAudio).

Usage:
    python pipeline.py run-all                # Process all new scripts in Script/
    python pipeline.py run "Podcasts/Script/file.txt"  # Process a single script
    python pipeline.py watch                  # Monitor Script/ folder for new files
    python pipeline.py list-voices            # List available TTS voices
"""

import os
import re
import sys
import time
import asyncio
import shutil
import argparse
from pathlib import Path
from typing import Optional, Tuple

import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

import edge_tts
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TALB, TRCK, TCON, APIC, ID3NoHeaderError

# Load environment variables
load_dotenv()

console = Console()

# Configuration from .env with fallback defaults
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-AndrewMultilingualNeural")
TTS_RATE = os.getenv("TTS_RATE", "+0%")
TTS_PITCH = os.getenv("TTS_PITCH", "+0Hz")
TTS_VOLUME = os.getenv("TTS_VOLUME", "+0%")

DEFAULT_ARTIST = os.getenv("DEFAULT_ARTIST", "AI")
DEFAULT_ALBUM_ARTIST = os.getenv("DEFAULT_ALBUM_ARTIST", "AI")
DEFAULT_ALBUM = os.getenv("DEFAULT_ALBUM", "AI Podcasts")
DEFAULT_GENRE = os.getenv("DEFAULT_GENRE", "Podcast")

SCRIPT_DIR = Path(os.getenv("SCRIPT_DIR", "Podcasts/Script"))
AUDIO_DIR = Path(os.getenv("AUDIO_DIR", "Podcasts/Audio"))
ASSETS_DIR = Path(os.getenv("ASSETS_DIR", "assets"))
DONE_DIR = Path(os.getenv("DONE_DIR", "Podcasts/Script/Done"))
MOVE_TO_DONE = os.getenv("MOVE_TO_DONE", "true").strip().lower() in ("true", "1", "yes")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TELEGRAM_CAPTION_PREFIX = os.getenv("TELEGRAM_CAPTION_PREFIX", "🎙 *New podcast episode*").strip()
TELEGRAM_INCLUDE_HASHTAGS = os.getenv("TELEGRAM_INCLUDE_HASHTAGS", "#podcast #AI").strip()


def parse_filename(filepath: Path) -> Tuple[Optional[str], str]:
    """
    Extracts optional episode track number and clean title from filename.
    e.g. '2. The Architecture of Emptiness.txt' -> ('2', 'The Architecture of Emptiness')
         'The Big Bang.txt' -> (None, 'The Big Bang')
    """
    stem = filepath.stem
    match = re.match(r"^(\d+)[\.\s\-_]+(.*)$", stem)
    if match:
        track_num = match.group(1).strip()
        title = match.group(2).strip()
        return track_num, title
    return None, stem.strip()


def find_cover_image(script_path: Path) -> Optional[Path]:
    """Finds an associated cover art image (specific to script or default in assets)."""
    # 1. Check for script-specific cover (e.g., Podcasts/Script/2. Episode title.jpg)
    for ext in (".jpg", ".jpeg", ".png"):
        specific = script_path.with_suffix(ext)
        if specific.is_file():
            return specific
    
    # 2. Check assets directory
    if ASSETS_DIR.exists():
        for name in ("cover.jpg", "cover.png", "default_cover.jpg", "default_cover.png"):
            cover = ASSETS_DIR / name
            if cover.is_file():
                return cover
    return None


async def synthesize_speech(
    text_path: Path,
    output_audio_path: Path,
    voice: str = TTS_VOICE,
    rate: str = TTS_RATE,
    pitch: str = TTS_PITCH,
    volume: str = TTS_VOLUME,
) -> bool:
    """Synthesizes text into MP3 using edge-tts."""
    try:
        with open(text_path, "r", encoding="utf-8") as f:
            text = f.read().strip()

        if not text:
            console.print(f"[yellow]⚠️ Script file is empty: {text_path}[/yellow]")
            return False

        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            pitch=pitch,
            volume=volume,
        )
        await communicate.save(str(output_audio_path))
        return True
    except Exception as e:
        console.print(f"[red]❌ Synthesis error for {text_path.name}: {e}[/red]")
        return False


def tag_audio(
    mp3_path: Path,
    title: str,
    track: Optional[str] = None,
    artist: str = DEFAULT_ARTIST,
    album_artist: str = DEFAULT_ALBUM_ARTIST,
    album: str = DEFAULT_ALBUM,
    genre: str = DEFAULT_GENRE,
    cover_image_path: Optional[Path] = None,
) -> bool:
    """Writes ID3v2 metadata tags into the MP3 file using mutagen."""
    try:
        try:
            tags = ID3(str(mp3_path))
        except ID3NoHeaderError:
            tags = ID3()

        tags.add(TIT2(encoding=3, text=title))
        tags.add(TPE1(encoding=3, text=artist))
        tags.add(TPE2(encoding=3, text=album_artist))
        tags.add(TALB(encoding=3, text=album))
        tags.add(TCON(encoding=3, text=genre))

        if track:
            tags.add(TRCK(encoding=3, text=str(track)))

        # Attach cover art if available
        if cover_image_path and cover_image_path.is_file():
            mime = "image/png" if cover_image_path.suffix.lower() == ".png" else "image/jpeg"
            with open(cover_image_path, "rb") as img:
                tags.add(
                    APIC(
                        encoding=3,
                        mime=mime,
                        type=3,  # Front cover
                        desc="Cover",
                        data=img.read(),
                    )
                )

        tags.save(str(mp3_path))
        return True
    except Exception as e:
        console.print(f"[red]❌ Tagging error for {mp3_path.name}: {e}[/red]")
        return False


def publish_to_telegram(
    mp3_path: Path,
    title: str,
    performer: str = DEFAULT_ARTIST,
    track: Optional[str] = None,
) -> bool:
    """Publishes audio to Telegram using the official Bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        console.print("[dim]ℹ️ Telegram credentials not set in .env — skipping Telegram publication.[/dim]")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendAudio"

    # Format caption
    caption_lines = []
    if TELEGRAM_CAPTION_PREFIX:
        caption_lines.append(TELEGRAM_CAPTION_PREFIX)
    
    episode_info = f"#{track}. " if track else ""
    caption_lines.append(f"*{episode_info}{title}*")
    
    if TELEGRAM_INCLUDE_HASHTAGS:
        caption_lines.append(f"\n{TELEGRAM_INCLUDE_HASHTAGS}")
    
    caption = "\n".join(caption_lines)

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "title": title,
        "performer": performer,
        "caption": caption,
        "parse_mode": "Markdown",
    }

    try:
        with open(mp3_path, "rb") as audio_file:
            files = {"audio": (mp3_path.name, audio_file, "audio/mpeg")}
            response = requests.post(url, data=data, files=files, timeout=120)
            result = response.json()

        if response.status_code == 200 and result.get("ok"):
            console.print(f"[green]🚀 Successfully broadcasted to Telegram (Chat: {TELEGRAM_CHAT_ID})[/green]")
            return True
        else:
            description = result.get("description", "Unknown error")
            console.print(f"[red]❌ Telegram API error: {description}[/red]")
            return False
    except Exception as e:
        console.print(f"[red]❌ Telegram upload exception: {e}[/red]")
        return False


def list_inbox_scripts() -> list:
    """Lists .txt scripts located directly in SCRIPT_DIR (subfolders such as Done/ are ignored)."""
    return sorted(p for p in SCRIPT_DIR.glob("*.txt") if p.is_file())


def archive_script(script_path: Path) -> Optional[Path]:
    """Moves a processed script (and its companion cover image) into DONE_DIR."""
    try:
        DONE_DIR.mkdir(parents=True, exist_ok=True)
        moved_script = None
        candidates = [script_path] + [script_path.with_suffix(e) for e in (".jpg", ".jpeg", ".png")]
        for src in candidates:
            if not src.is_file():
                continue
            dest = DONE_DIR / src.name
            if dest.exists():
                dest = DONE_DIR / f"{src.stem}.{time.strftime('%Y%m%d-%H%M%S')}{src.suffix}"
            shutil.move(str(src), str(dest))
            if src == script_path:
                moved_script = dest
        console.print(f"[dim]📁 Archived to {DONE_DIR}/[/dim]")
        return moved_script
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


async def process_file(
    script_path: Path,
    skip_tg: bool = False,
    force: bool = False,
    voice: str = TTS_VOICE,
    rate: str = TTS_RATE,
    move_done: Optional[bool] = None,
) -> bool:
    """Processes a single script: Text -> Audio -> ID3 Tag -> Telegram -> archive to Done/."""
    if move_done is None:
        move_done = MOVE_TO_DONE
    track, title = parse_filename(script_path)
    output_mp3 = AUDIO_DIR / f"{script_path.stem}.mp3"

    console.print(Panel(
        f"[bold cyan]Episode:[/bold cyan] {script_path.name}\n"
        f"[bold cyan]Title:[/bold cyan] {title}\n"
        f"[bold cyan]Track:[/bold cyan] {track or 'None'}\n"
        f"[bold cyan]Voice:[/bold cyan] {voice} ({rate})",
        title="🎙️ Processing Episode",
        border_style="cyan"
    ))

    if output_mp3.exists() and not force:
        console.print(f"[yellow]⏩ Audio already exists: {output_mp3.name} (use --force to overwrite)[/yellow]")
    else:
        with console.status(f"[bold green]Synthesizing speech with {voice}..."):
            success = await synthesize_speech(
                text_path=script_path,
                output_audio_path=output_mp3,
                voice=voice,
                rate=rate,
            )
            if not success:
                return False
        console.print(f"[green]✅ Audio generated: {output_mp3.name}[/green]")

    # Tagging
    cover_image = find_cover_image(script_path)
    with console.status("[bold blue]Writing ID3 tags (Title, Artist=AI, Album Artist=AI)..."):
        tag_success = tag_audio(
            mp3_path=output_mp3,
            title=title,
            track=track,
            artist=DEFAULT_ARTIST,
            album_artist=DEFAULT_ALBUM_ARTIST,
            album=DEFAULT_ALBUM,
            genre=DEFAULT_GENRE,
            cover_image_path=cover_image,
        )
        if tag_success:
            console.print(f"[blue]🏷️ ID3 metadata tagged successfully.[/blue]")

    # Telegram Broadcast
    tg_ok = True
    if not skip_tg:
        with console.status("[bold magenta]Broadcasting to Telegram..."):
            sent = publish_to_telegram(
                mp3_path=output_mp3,
                title=title,
                performer=DEFAULT_ARTIST,
                track=track,
            )
        # A failed upload (as opposed to unconfigured credentials) keeps the script in the inbox for retry.
        tg_ok = sent or not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

    if not (tag_success and tg_ok):
        console.print("[yellow]⚠️ Episode not fully processed; script left in place for retry.[/yellow]")
        return False

    if move_done:
        archive_script(script_path)

    return True


async def process_all_new(skip_tg: bool = False, force: bool = False, move_done: Optional[bool] = None):
    """Processes pending scripts in SCRIPT_DIR (scripts already archived to Done/ are never touched)."""
    if move_done is None:
        move_done = MOVE_TO_DONE
    if not SCRIPT_DIR.exists():
        console.print(f"[red]❌ Script directory '{SCRIPT_DIR}' not found.[/red]")
        return

    scripts = list_inbox_scripts()
    if not scripts:
        console.print(f"[yellow]ℹ️ No new .txt scripts found in '{SCRIPT_DIR}'.[/yellow]")
        return

    console.print(f"[bold]Found {len(scripts)} script(s) in {SCRIPT_DIR}/[/bold]")

    processed_count = 0
    for script in scripts:
        output_mp3 = AUDIO_DIR / f"{script.stem}.mp3"
        # With archiving on, anything left in the inbox is pending (e.g. a failed upload to retry).
        # With archiving off, an existing MP3 means the episode was already handled.
        if force or move_done or not output_mp3.exists():
            if await process_file(script, skip_tg=skip_tg, force=force, move_done=move_done):
                processed_count += 1
        else:
            console.print(f"[dim]⏩ Skipping already generated: {script.name}[/dim]")

    console.print(f"\n[bold green]🎉 Done! Processed {processed_count} new episode(s).[/bold green]")


async def watch_folder(poll_interval: int = 3, skip_tg: bool = False, move_done: Optional[bool] = None):
    """Watches SCRIPT_DIR (top level only, Done/ is ignored) for newly added or modified .txt files."""
    console.print(Panel(
        f"👀 Watching folder: [bold cyan]{SCRIPT_DIR.resolve()}[/bold cyan]\n"
        f"Drop any [bold].txt[/bold] script here to automatically synthesize, tag, and publish.\n"
        f"Press [bold red]Ctrl+C[/bold red] to stop.",
        title="🤖 AI Podcast Watcher Active",
        border_style="green"
    ))

    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    seen_mtimes = {}
    # Initialize with current files so we only trigger on new/updated ones
    for p in list_inbox_scripts():
        seen_mtimes[p] = p.stat().st_mtime

    try:
        while True:
            await asyncio.sleep(poll_interval)
            current_files = list_inbox_scripts()
            # Forget files that were archived or deleted
            for gone in [k for k in seen_mtimes if k not in current_files]:
                del seen_mtimes[gone]
            for p in current_files:
                mtime = p.stat().st_mtime
                if p not in seen_mtimes:
                    console.print(f"\n[bold green]✨ New script detected: {p.name}[/bold green]")
                    seen_mtimes[p] = mtime
                    if not await wait_until_stable(p):
                        continue
                    await process_file(p, skip_tg=skip_tg, move_done=move_done)
                elif mtime > seen_mtimes[p]:
                    console.print(f"\n[bold yellow]📝 Script modified: {p.name}[/bold yellow]")
                    seen_mtimes[p] = mtime
                    if not await wait_until_stable(p):
                        continue
                    await process_file(p, skip_tg=skip_tg, force=True, move_done=move_done)
    except KeyboardInterrupt:
        console.print("\n[yellow]Watcher stopped by user.[/yellow]")


async def list_voices(lang_filter: Optional[str] = None):
    """Lists available Edge-TTS voices."""
    voices = await edge_tts.list_voices()
    if lang_filter:
        voices = [v for v in voices if lang_filter.lower() in v["Locale"].lower() or lang_filter.lower() in v["ShortName"].lower()]

    table = Table(title=f"Edge-TTS Voices ({len(voices)} available)")
    table.add_column("Short Name", style="cyan")
    table.add_column("Gender", style="magenta")
    table.add_column("Locale", style="green")

    for v in voices[:30]:  # Limit output
        table.add_row(v["ShortName"], v["Gender"], v["Locale"])

    console.print(table)
    if len(voices) > 30:
        console.print(f"[dim]...and {len(voices) - 30} more. Use --filter to narrow down.[/dim]")


def main():
    parser = argparse.ArgumentParser(description="AI Podcast Automation Pipeline")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run command (single file)
    run_parser = subparsers.add_parser("run", help="Process a single script file")
    run_parser.add_argument("file", type=str, help="Path to the script .txt file")
    run_parser.add_argument("--voice", type=str, default=TTS_VOICE, help="TTS voice override")
    run_parser.add_argument("--rate", type=str, default=TTS_RATE, help="Speed rate (e.g. +10%%)")
    run_parser.add_argument("--no-tg", action="store_true", help="Skip Telegram broadcast")
    run_parser.add_argument("--force", action="store_true", help="Overwrite existing audio")

    # run-all command
    all_parser = subparsers.add_parser("run-all", help="Process all new scripts in Script/ folder")
    all_parser.add_argument("--no-tg", action="store_true", help="Skip Telegram broadcast")
    all_parser.add_argument("--force", action="store_true", help="Re-generate even if audio exists")

    # watch command
    watch_parser = subparsers.add_parser("watch", help="Watch Script/ folder and process new files in real-time")
    watch_parser.add_argument("--interval", type=int, default=3, help="Polling interval in seconds")
    watch_parser.add_argument("--no-tg", action="store_true", help="Skip Telegram broadcast")

    # list-voices command
    voice_parser = subparsers.add_parser("list-voices", help="List available Edge-TTS voices")
    voice_parser.add_argument("--filter", type=str, default=None, help="Filter by locale or name (e.g. 'ru' or 'en')")

    for sub in (run_parser, all_parser, watch_parser):
        sub.add_argument("--move", action=argparse.BooleanOptionalAction, default=None,
                         help="Move processed scripts to Done/ (default: MOVE_TO_DONE from .env)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "run":
        file_path = Path(args.file)
        if not file_path.is_file():
            console.print(f"[red]❌ File not found: {file_path}[/red]")
            sys.exit(1)
        asyncio.run(process_file(file_path, skip_tg=args.no_tg, force=args.force, voice=args.voice, rate=args.rate, move_done=args.move))

    elif args.command == "run-all":
        asyncio.run(process_all_new(skip_tg=args.no_tg, force=args.force, move_done=args.move))

    elif args.command == "watch":
        try:
            asyncio.run(watch_folder(poll_interval=args.interval, skip_tg=args.no_tg, move_done=args.move))
        except KeyboardInterrupt:
            console.print("\n[yellow]Watcher stopped by user.[/yellow]")

    elif args.command == "list-voices":
        asyncio.run(list_voices(lang_filter=args.filter))


if __name__ == "__main__":
    main()

