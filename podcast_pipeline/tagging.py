"""ID3v2 tagging via mutagen."""

from __future__ import annotations

from pathlib import Path

from mutagen.id3 import ID3, TALB, TCON, TIT2, TPE1, TPE2, TRCK, ID3NoHeaderError

from podcast_pipeline.config import Settings, console

UTF8 = 3


def tag_audio(
    mp3_path: Path,
    title: str,
    cfg: Settings,
    track: str | None = None,
) -> bool:
    """Writes ID3v2 metadata (title, artist, album, genre, track) into the MP3."""
    try:
        try:
            tags = ID3(str(mp3_path))
        except ID3NoHeaderError:
            tags = ID3()

        tags.add(TIT2(encoding=UTF8, text=title))
        tags.add(TPE1(encoding=UTF8, text=cfg.artist))
        tags.add(TPE2(encoding=UTF8, text=cfg.album_artist))
        tags.add(TALB(encoding=UTF8, text=cfg.album))
        tags.add(TCON(encoding=UTF8, text=cfg.genre))

        if track:
            tags.add(TRCK(encoding=UTF8, text=str(track)))

        tags.save(str(mp3_path))
        return True
    except Exception as e:
        console.print(f"[red]❌ Tagging error for {mp3_path.name}: {e}[/red]")
        return False
