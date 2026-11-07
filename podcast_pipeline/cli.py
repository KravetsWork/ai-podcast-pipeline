"""Command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from podcast_pipeline import __version__
from podcast_pipeline.config import Settings, console
from podcast_pipeline.tts import list_voices
from podcast_pipeline.workflow import process_all_new, process_file, watch_folder


def build_parser(cfg: Settings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline.py", description="AI Podcast Automation Pipeline")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", help="Available commands")

    run_p = sub.add_parser("run", help="Process a single script file")
    run_p.add_argument("file", type=str, help="Path to the script .txt file")
    run_p.add_argument("--voice", type=str, default=cfg.tts_voice, help="TTS voice override")
    run_p.add_argument("--rate", type=str, default=cfg.tts_rate, help="Speed rate (e.g. +10%%)")
    run_p.add_argument("--no-tg", action="store_true", help="Skip Telegram broadcast")
    run_p.add_argument("--force", action="store_true", help="Overwrite existing audio")

    all_p = sub.add_parser("run-all", help="Process all new scripts in the Script/ folder")
    all_p.add_argument("--no-tg", action="store_true", help="Skip Telegram broadcast")
    all_p.add_argument("--force", action="store_true", help="Re-generate even if audio exists")

    watch_p = sub.add_parser("watch", help="Watch the Script/ folder and process new files in real time")
    watch_p.add_argument("--interval", type=int, default=3, help="Polling interval in seconds")
    watch_p.add_argument("--no-tg", action="store_true", help="Skip Telegram broadcast")

    voice_p = sub.add_parser("list-voices", help="List available Edge-TTS voices")
    voice_p.add_argument("--filter", type=str, default=None, help="Filter by locale or name (e.g. 'uk' or 'en')")

    for p in (run_p, all_p, watch_p):
        p.add_argument(
            "--move",
            action=argparse.BooleanOptionalAction,
            default=None,
            help="Move processed scripts to Done/ (default: MOVE_TO_DONE from .env)",
        )

    for p in (all_p, watch_p):
        p.add_argument(
            "--jobs",
            type=int,
            default=cfg.max_jobs,
            help=f"Number of script files to process in parallel (default: {cfg.max_jobs})",
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    cfg = Settings.from_env()
    parser = build_parser(cfg)
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "run":
        file_path = Path(args.file)
        if not file_path.is_file():
            console.print(f"[red]❌ File not found: {file_path}[/red]")
            return 1
        ok = asyncio.run(
            process_file(
                file_path,
                cfg,
                skip_tg=args.no_tg,
                force=args.force,
                voice=args.voice,
                rate=args.rate,
                move_done=args.move,
            )
        )
        return 0 if ok else 1

    if args.command == "run-all":
        asyncio.run(process_all_new(cfg, skip_tg=args.no_tg, force=args.force, move_done=args.move, jobs=args.jobs))
    elif args.command == "watch":
        asyncio.run(
            watch_folder(cfg, poll_interval=args.interval, skip_tg=args.no_tg, move_done=args.move, jobs=args.jobs)
        )
    elif args.command == "list-voices":
        asyncio.run(list_voices(lang_filter=args.filter))
    return 0


def run() -> None:
    """Console entry point with clean Ctrl+C handling."""
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        sys.exit(130)
