"""Orchestration: script -> audio -> tags -> Telegram -> archive; parallel batch and watch modes."""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich.panel import Panel
from rich.progress import Progress

from podcast_pipeline.config import Settings, console
from podcast_pipeline.episodes import (
    archive_script,
    find_existing_mp3,
    list_inbox_scripts,
    parse_filename,
    resolve_episode,
    wait_until_stable,
)
from podcast_pipeline.tagging import tag_audio
from podcast_pipeline.telegram import publish_to_telegram
from podcast_pipeline.tts import make_progress, synthesize_speech

# Any MP3 smaller than 4 KB is only an ID3 header stub and should be regenerated.
MIN_VALID_MP3_BYTES = 4096

# Serializes episode numbering, tagging, and Telegram publishing so parallel scripts
# are numbered and posted to Telegram in exact completion order (e.g. 11, 12, 13, 14).
_publish_lock = asyncio.Lock()


def is_valid_mp3(path: Path | None) -> bool:
    """Returns True if the MP3 exists and contains actual audio frames beyond an ID3 tag header."""
    return path is not None and path.is_file() and path.stat().st_size >= MIN_VALID_MP3_BYTES


async def process_file(
    script_path: Path,
    cfg: Settings,
    skip_tg: bool = False,
    force: bool = False,
    voice: str | None = None,
    rate: str | None = None,
    move_done: bool | None = None,
    progress: Progress | None = None,
) -> bool:
    """Processes one script: text -> audio -> assign number -> ID3 tags -> Telegram -> archive."""
    move_done = cfg.move_to_done if move_done is None else move_done
    voice = voice or cfg.tts_voice
    rate = rate or cfg.tts_rate
    raw_track, raw_title = parse_filename(script_path)

    console.print(
        Panel(
            f"[bold cyan]Episode:[/bold cyan] {script_path.name}\n"
            f"[bold cyan]Title:[/bold cyan] {raw_title}\n"
            f"[bold cyan]Track:[/bold cyan] {raw_track or 'Auto (assigned on completion)'}\n"
            f"[bold cyan]Voice:[/bold cyan] {voice}",
            title="🎙️ Processing Episode",
            border_style="cyan",
        )
    )

    existing_mp3 = find_existing_mp3(script_path, cfg)
    temp_mp3: Path | None = None

    if is_valid_mp3(existing_mp3) and not force:
        console.print(f"[yellow]⏩ Audio already exists: {existing_mp3.name} (use --force to overwrite)[/yellow]")
    else:
        temp_mp3 = cfg.audio_dir / f".{script_path.stem}.mp3.tmp"
        ok = await synthesize_speech(script_path, temp_mp3, cfg, voice=voice, rate=rate, progress=progress)
        if not ok:
            return False

    async with _publish_lock:
        track, title, output_mp3 = resolve_episode(script_path, cfg)
        if temp_mp3 is not None:
            temp_mp3.replace(output_mp3)
            console.print(f"[green]✅ Audio generated: {output_mp3.name}[/green]")

        tagged = tag_audio(output_mp3, title, cfg, track=track)
        if tagged:
            console.print(f"[blue]🏷️ ID3 metadata tagged: {output_mp3.name}[/blue]")

        tg_ok = True
        if not skip_tg:
            sent = publish_to_telegram(output_mp3, title, cfg, track=track)
            # A failed upload (as opposed to unconfigured credentials) keeps the script in the inbox for retry.
            tg_ok = sent or not cfg.telegram_enabled

        if not (tagged and tg_ok):
            console.print(f"[yellow]⚠️ '{script_path.name}' not fully processed; left in place for retry.[/yellow]")
            return False

        if move_done:
            archive_script(script_path, cfg, new_stem=output_mp3.stem)
        return True


async def process_all_new(
    cfg: Settings,
    skip_tg: bool = False,
    force: bool = False,
    move_done: bool | None = None,
    jobs: int | None = None,
) -> int:
    """Processes pending scripts in the script folder (up to `jobs` files concurrently)."""
    move_done = cfg.move_to_done if move_done is None else move_done
    worker_count = max(1, cfg.max_jobs if jobs is None else jobs)

    if not cfg.script_dir.exists():
        console.print(f"[red]❌ Script directory '{cfg.script_dir}' not found.[/red]")
        return 0

    scripts = list_inbox_scripts(cfg)
    if not scripts:
        console.print(f"[yellow]ℹ️ No new .txt scripts found in '{cfg.script_dir}'.[/yellow]")
        return 0

    pending = [s for s in scripts if force or move_done or not is_valid_mp3(find_existing_mp3(s, cfg))]
    if not pending:
        console.print("\n[bold green]🎉 Done! Processed 0 new episode(s).[/bold green]")
        return 0

    console.print(
        f"[bold]Found {len(pending)} script(s) in {cfg.script_dir}/ (running up to {worker_count} in parallel)[/bold]"
    )

    semaphore = asyncio.Semaphore(worker_count)

    with make_progress() as progress:

        async def _run_one(script: Path) -> bool:
            async with semaphore:
                return await process_file(
                    script, cfg, skip_tg=skip_tg, force=force, move_done=move_done, progress=progress
                )

        results = await asyncio.gather(*(_run_one(s) for s in pending))

    processed = sum(results)
    console.print(f"\n[bold green]🎉 Done! Processed {processed} new episode(s).[/bold green]")
    return processed


async def watch_folder(
    cfg: Settings,
    poll_interval: int = 3,
    skip_tg: bool = False,
    move_done: bool | None = None,
    jobs: int | None = None,
) -> None:
    """Watches the script folder and processes new or modified .txt files concurrently."""
    worker_count = max(1, cfg.max_jobs if jobs is None else jobs)
    console.print(
        Panel(
            f"👀 Watching folder: [bold cyan]{cfg.script_dir.resolve()}[/bold cyan]\n"
            f"Parallel file workers: [bold cyan]{worker_count}[/bold cyan]\n"
            "Drop any [bold].txt[/bold] script here to automatically synthesize, tag, and publish.\n"
            "Press [bold red]Ctrl+C[/bold red] to stop.",
            title="🤖 AI Podcast Watcher Active",
            border_style="green",
        )
    )

    cfg.script_dir.mkdir(parents=True, exist_ok=True)
    cfg.audio_dir.mkdir(parents=True, exist_ok=True)

    seen = {p: p.stat().st_mtime for p in list_inbox_scripts(cfg)}
    active_tasks: dict[Path, asyncio.Task[bool]] = {}
    semaphore = asyncio.Semaphore(worker_count)

    with make_progress() as progress:

        async def _handle_script(path: Path, force: bool) -> bool:
            try:
                if not await wait_until_stable(path):
                    return False
                async with semaphore:
                    return await process_file(
                        path, cfg, skip_tg=skip_tg, force=force, move_done=move_done, progress=progress
                    )
            finally:
                active_tasks.pop(path, None)

        try:
            while True:
                await asyncio.sleep(poll_interval)
                current = list_inbox_scripts(cfg)
                for gone in [k for k in seen if k not in current and k not in active_tasks]:
                    del seen[gone]
                for p in current:
                    if p in active_tasks:
                        continue
                    try:
                        mtime = p.stat().st_mtime
                    except FileNotFoundError:
                        continue
                    if p not in seen:
                        console.print(f"\n[bold green]✨ New script detected: {p.name}[/bold green]")
                        force = False
                    elif mtime > seen[p]:
                        console.print(f"\n[bold yellow]📝 Script modified: {p.name}[/bold yellow]")
                        force = True
                    else:
                        continue
                    seen[p] = mtime
                    active_tasks[p] = asyncio.create_task(_handle_script(p, force))
        except (KeyboardInterrupt, asyncio.CancelledError):
            for task in active_tasks.values():
                task.cancel()
            if active_tasks:
                await asyncio.gather(*active_tasks.values(), return_exceptions=True)
            console.print("\n[yellow]Watcher stopped by user.[/yellow]")
