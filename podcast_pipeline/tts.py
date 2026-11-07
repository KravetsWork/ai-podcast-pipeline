"""Lightweight speech synthesis using default edge-tts with per-chunk retry and live progress."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from pathlib import Path

import edge_tts
from edge_tts.communicate import (
    escape as xml_escape,
)
from edge_tts.communicate import (
    remove_incompatible_characters,
    split_text_by_byte_length,
)
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from podcast_pipeline.config import Settings, console

CHUNK_MAX_BYTES = 4096
CHUNK_RETRIES = 5
RETRY_WAIT_SECONDS = 15


def make_progress() -> Progress:
    """Creates a Rich Progress display that can track one or multiple files simultaneously."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold green]{task.description}"),
        BarColumn(bar_width=25),
        TaskProgressColumn(),
        TextColumn("[cyan]{task.fields[kb]} KB[/cyan]"),
        TextColumn("[dim]• Elapsed:[/dim]"),
        TimeElapsedColumn(),
        TextColumn("[dim]• ETA:[/dim]"),
        TimeRemainingColumn(),
        console=console,
    )


async def synthesize_speech(
    text_path: Path,
    output_audio_path: Path,
    cfg: Settings,
    voice: str | None = None,
    rate: str | None = None,
    progress: Progress | None = None,
) -> bool:
    """Synthesizes a text script into an MP3 sequentially with per-chunk retry."""
    voice = voice or cfg.tts_voice
    rate = rate or cfg.tts_rate
    part_path = output_audio_path.with_suffix(".mp3.part")

    try:
        text = text_path.read_text(encoding="utf-8-sig").strip()
        if not text:
            console.print(f"[yellow]⚠️ Script file is empty: {text_path}[/yellow]")
            return False

        chunks = list(
            split_text_by_byte_length(
                xml_escape(remove_incompatible_characters(text)),
                CHUNK_MAX_BYTES,
            )
        )
        if not chunks:
            console.print(f"[yellow]⚠️ Script file has no synthesizable text: {text_path}[/yellow]")
            return False

        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        total_bytes = max(sum(len(c) for c in chunks), 1)
        total_chunks = len(chunks)
        audio_bytes = 0
        completed_bytes = 0
        ctx = nullcontext(progress) if progress is not None else make_progress()

        with ctx as prog, open(part_path, "wb") as audio_file:
            task_id = prog.add_task(f"{text_path.name} [1/{total_chunks}]", total=total_bytes, kb=0)
            try:
                for idx, chunk_bytes in enumerate(chunks, 1):
                    chunk_len = len(chunk_bytes)
                    prog.update(task_id, description=f"{text_path.name} [{idx}/{total_chunks}]")

                    for attempt in range(1, CHUNK_RETRIES + 1):
                        try:
                            comm = edge_tts.Communicate(
                                text="",
                                voice=voice,
                                rate=rate,
                                pitch=cfg.tts_pitch,
                                volume=cfg.tts_volume,
                            )
                            comm.texts = [chunk_bytes]
                            buf = bytearray()
                            seen_in_chunk = 0

                            async for msg in comm.stream():
                                if msg["type"] == "audio":
                                    buf.extend(msg["data"])
                                    prog.update(task_id, kb=(audio_bytes + len(buf)) // 1024)
                                elif msg["type"] in ("WordBoundary", "SentenceBoundary"):
                                    step = len(msg.get("text", "").encode("utf-8")) + 1
                                    seen_in_chunk = min(seen_in_chunk + step, chunk_len)
                                    prog.update(task_id, completed=completed_bytes + seen_in_chunk)

                            if not buf:
                                raise RuntimeError("No audio received for chunk")

                            audio_file.write(buf)
                            audio_bytes += len(buf)
                            completed_bytes += chunk_len
                            prog.update(task_id, completed=completed_bytes, kb=audio_bytes // 1024)
                            break
                        except Exception:
                            if attempt == CHUNK_RETRIES:
                                raise
                            wait = RETRY_WAIT_SECONDS * attempt
                            retry_desc = (
                                f"{text_path.name} [{idx}/{total_chunks} retry {attempt}/{CHUNK_RETRIES} in {wait}s]"
                            )
                            prog.update(
                                task_id,
                                completed=completed_bytes,
                                kb=audio_bytes // 1024,
                                description=retry_desc,
                            )
                            await asyncio.sleep(wait)
            finally:
                if progress is not None:
                    prog.remove_task(task_id)

        if audio_bytes == 0:
            raise RuntimeError("No audio data was written by edge-tts")

        part_path.replace(output_audio_path)
        return True
    except (asyncio.CancelledError, KeyboardInterrupt):
        part_path.unlink(missing_ok=True)
        raise
    except Exception as e:
        part_path.unlink(missing_ok=True)
        console.print(f"[red]❌ Synthesis error for {text_path.name}: {e}[/red]")
        return False


async def list_voices(lang_filter: str | None = None, limit: int = 30) -> None:
    """Prints available Edge-TTS voices, optionally filtered by locale or name."""
    from rich.table import Table

    voices = await edge_tts.list_voices()
    if lang_filter:
        needle = lang_filter.lower()
        voices = [v for v in voices if needle in v["Locale"].lower() or needle in v["ShortName"].lower()]

    table = Table(title=f"Edge-TTS Voices ({len(voices)} available)")
    table.add_column("Short Name", style="cyan")
    table.add_column("Gender", style="magenta")
    table.add_column("Locale", style="green")
    for v in voices[:limit]:
        table.add_row(v["ShortName"], v["Gender"], v["Locale"])

    console.print(table)
    if len(voices) > limit:
        console.print(f"[dim]...and {len(voices) - limit} more. Use --filter to narrow down.[/dim]")
