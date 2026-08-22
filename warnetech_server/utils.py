"""Helper functions: JSON/NDJSON handling, timestamps, ID generation,
checksum calculation, and simple file IO.

Kept deliberately narrower than warnetech_control_plane/utils.py — the
server has no need for compression/encryption/Parquet helpers, only the
plumbing its routes and integrations actually use.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Iterator

# -- timestamps -----------------------------------------------------------------


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def now_epoch_ms() -> int:
    return int(time.time() * 1000)


# -- ID generation --------------------------------------------------------------


def new_id(prefix: str = "req") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


# -- JSON / NDJSON ----------------------------------------------------------------


def to_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, default=str, separators=(",", ":")).encode("utf-8")


def from_json_bytes(data: bytes) -> Any:
    if not data:
        return None
    return json.loads(data.decode("utf-8"))


def to_ndjson(records: Iterable[dict]) -> str:
    return "\n".join(json.dumps(r, default=str, separators=(",", ":")) for r in records)


def from_ndjson(text: str) -> Iterator[dict]:
    for line in text.splitlines():
        line = line.strip()
        if line:
            yield json.loads(line)


# -- checksum -----------------------------------------------------------------------


def checksum(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


# -- file IO -----------------------------------------------------------------------


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_json(path: str | Path, obj: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(to_json_bytes(obj))


def read_json(path: str | Path) -> Any:
    return from_json_bytes(Path(path).read_bytes())


def write_ndjson(path: str | Path, records: Iterable[dict]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, default=str, separators=(",", ":")))
            fh.write("\n")
            count += 1
    return count
