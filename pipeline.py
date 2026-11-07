"""Backward-compatible entry point: `python pipeline.py <command>`.

The implementation lives in the `podcast_pipeline` package.
"""

from podcast_pipeline.cli import run

if __name__ == "__main__":
    run()
