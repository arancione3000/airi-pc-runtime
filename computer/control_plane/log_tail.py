from __future__ import annotations

import os
from pathlib import Path

MAX_OUTPUT_CHARS = 1_000_000


def read_log_tail(path: Path, max_chars: int = 20_000) -> str:
    """Read only a bounded UTF-8 suffix, even when a job produces huge logs."""
    limit = min(MAX_OUTPUT_CHARS, max(1, int(max_chars)))
    with path.open('rb') as log:
        size = log.seek(0, os.SEEK_END)
        log.seek(max(0, size - limit * 4))
        return log.read(limit * 4).decode('utf-8', errors='replace')[-limit:]
