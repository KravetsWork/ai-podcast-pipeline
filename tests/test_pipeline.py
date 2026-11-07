from pathlib import Path

import pytest

from podcast_pipeline.config import Settings
from podcast_pipeline.episodes import archive_script, list_inbox_scripts, parse_filename, resolve_episode
from podcast_pipeline.telegram import build_caption
from podcast_pipeline.tts import synthesize_speech
from podcast_pipeline.workflow import is_valid_mp3


def _run_sync(coro):
    """Drives a pure-Python coroutine to completion without creating an OS event loop socket."""
    try:
        coro.send(None)
    except StopIteration as stop:
        return stop.value
    raise RuntimeError("Coroutine yielded unexpectedly")


@pytest.fixture
def cfg(tmp_path: Path) -> Settings:
    return Settings(
        script_dir=tmp_path / "Script",
        audio_dir=tmp_path / "Audio",
        done_dir=tmp_path / "Script" / "Done",
    )


@pytest.mark.parametrize(
    "name, expected",
    [
        ("2. The Architecture.txt", ("2", "The Architecture")),
        ("10 - Ten.txt", ("10", "Ten")),
        ("The Big Bang.txt", (None, "The Big Bang")),
        ("3. Привіт, світе.txt", ("3", "Привіт, світе")),
    ],
)
def test_parse_filename(name, expected):
    assert parse_filename(Path(name)) == expected


def test_auto_numbering_uses_highest_plus_one(cfg):
    cfg.audio_dir.mkdir(parents=True)
    (cfg.audio_dir / "1. First.mp3").touch()
    (cfg.audio_dir / "7. Seventh.mp3").touch()
    track, title, mp3 = resolve_episode(Path("New Episode.txt"), cfg)
    assert (track, title) == ("8", "New Episode")
    assert mp3 == cfg.audio_dir / "8. New Episode.mp3"


def test_completion_order_numbering_increments_as_mp3s_land(cfg):
    cfg.audio_dir.mkdir(parents=True)
    (cfg.audio_dir / "10. Existing.mp3").touch()
    # First script to finish claims 11 and writes its MP3
    t1, _, mp3_1 = resolve_episode(Path("Fast.txt"), cfg)
    mp3_1.touch()
    # Second script to finish sees 11 on disk and claims 12
    t2, _, mp3_2 = resolve_episode(Path("Slow.txt"), cfg)
    mp3_2.touch()
    assert (t1, t2) == ("11", "12")


def test_unnumbered_script_reuses_existing_mp3(cfg):
    cfg.audio_dir.mkdir(parents=True)
    (cfg.audio_dir / "4. Same Title.mp3").touch()
    assert resolve_episode(Path("Same Title.txt"), cfg)[0] == "4"


def test_manual_prefix_is_respected(cfg):
    track, _, mp3 = resolve_episode(Path("5. Manual.txt"), cfg)
    assert track == "5" and mp3.name == "5. Manual.mp3"


def test_inbox_ignores_done_folder(cfg):
    cfg.done_dir.mkdir(parents=True)
    (cfg.script_dir / "a.txt").write_text("x", encoding="utf-8")
    (cfg.done_dir / "old.txt").write_text("x", encoding="utf-8")
    assert [p.name for p in list_inbox_scripts(cfg)] == ["a.txt"]


def test_archive_moves_script_with_new_name(cfg):
    cfg.script_dir.mkdir(parents=True)
    script = cfg.script_dir / "Title.txt"
    script.write_text("x", encoding="utf-8")
    archive_script(script, cfg, new_stem="1. Title")
    assert (cfg.done_dir / "1. Title.txt").is_file()
    assert not script.exists()


def test_caption_format(cfg):
    caption = build_caption("Title", "3", cfg)
    assert "*#3. Title*" in caption
    assert caption.endswith(cfg.telegram_hashtags)


def test_synthesize_speech_writes_atomically(cfg, monkeypatch):
    class FakeCommunicate:
        def __init__(self, text, voice, **kwargs):
            self.texts = (b for b in [text.encode("utf-8")])

        async def stream(self):
            for part in self.texts:
                yield {"type": "SentenceBoundary", "text": part.decode("utf-8")}
                yield {"type": "audio", "data": b"FAKE_MP3_BYTES"}

    monkeypatch.setattr("podcast_pipeline.tts.edge_tts.Communicate", FakeCommunicate)
    cfg.script_dir.mkdir(parents=True)
    script = cfg.script_dir / "ep.txt"
    script.write_text("Hello world", encoding="utf-8")
    out = cfg.audio_dir / "1. ep.mp3"

    assert _run_sync(synthesize_speech(script, out, cfg)) is True
    assert out.read_bytes() == b"FAKE_MP3_BYTES"
    assert not out.with_suffix(".mp3.part").exists()


def test_synthesize_speech_fails_if_no_audio_written(cfg, monkeypatch):
    class EmptyCommunicate:
        def __init__(self, text, voice, **kwargs):
            self.texts = iter(())

        async def stream(self):
            if False:
                yield {}

    monkeypatch.setattr("podcast_pipeline.tts.edge_tts.Communicate", EmptyCommunicate)
    cfg.script_dir.mkdir(parents=True)
    script = cfg.script_dir / "ep.txt"
    script.write_text("Hello world", encoding="utf-8")
    out = cfg.audio_dir / "1. ep.mp3"

    assert _run_sync(synthesize_speech(script, out, cfg)) is False
    assert not out.exists()
    assert not out.with_suffix(".mp3.part").exists()


def test_is_valid_mp3_rejects_header_only_stubs(tmp_path):
    stub = tmp_path / "stub.mp3"
    stub.write_bytes(b"x" * 1200)
    valid = tmp_path / "valid.mp3"
    valid.write_bytes(b"x" * 5000)
    assert is_valid_mp3(stub) is False
    assert is_valid_mp3(valid) is True
