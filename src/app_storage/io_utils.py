"""
app_storage/io_utils.py
-----------------------
Crash-safe JSON writes.

Every store in ``app_storage`` used to write its JSON straight into the
target file (``path.write_text(json.dumps(...))``). A crash or power loss in
the middle of that write leaves a truncated file behind and the data is gone.

``write_json`` writes to a temporary file next to the target first and then
swaps it in with ``os.replace``, which is atomic on Windows, macOS and Linux.
A crash either leaves the old file untouched or the complete new one.

    from app_storage.io_utils import write_json

    write_json(path, {"key": "value"})
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

TMP_SUFFIX = ".tmp"


def write_json(path: Path | str, data: Any) -> None:
    """Write *data* as JSON to *path*, atomically.

    The parent folder is created if missing. On failure the temporary file is
    removed and the original file (if any) is left as it was.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + TMP_SUFFIX)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
