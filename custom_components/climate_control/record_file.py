"""FR-OBS-01: append the records to a file below the configuration directory (one JSON object per line)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

MAX_BYTES = (
    1_000_000  # one file; when it is full it replaces the previous one, so at most about 2 MB are kept
)


def append_records(path: Path, rows: Sequence[dict[str, Any]], max_bytes: int = MAX_BYTES) -> None:
    """Blocking, call from an executor. Rotates the file when it exceeds `max_bytes`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > max_bytes:
        path.replace(path.with_suffix(".jsonl.1"))
    with path.open("a", encoding="utf-8") as file:
        file.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
