"""Helper functions shared across engines: JSON/NDJSON, Parquet, encryption,
compression, hashing, timestamps, and file IO.

Only the standard library is required for core operation. Parquet export and
authenticated encryption use optional third-party packages (``pyarrow``,
``cryptography``) and raise a clear, actionable ``RuntimeError`` if a caller
reaches for them without the dependency installed, rather than silently
degrading to something insecure or lossy.
"""

from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any, Iterable, Iterator

# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def now_epoch_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# JSON / NDJSON
# ---------------------------------------------------------------------------


def to_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, default=str, separators=(",", ":")).encode("utf-8")


def from_json_bytes(data: bytes) -> Any:
    return json.loads(data.decode("utf-8"))


def to_ndjson(records: Iterable[dict]) -> str:
    return "\n".join(json.dumps(r, default=str, separators=(",", ":")) for r in records)


def from_ndjson(text: str) -> Iterator[dict]:
    for line in text.splitlines():
        line = line.strip()
        if line:
            yield json.loads(line)


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


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha1_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha1(data).hexdigest()


def hmac_sha256(key: bytes, data: bytes) -> str:
    return hmac.new(key, data, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Compression
# ---------------------------------------------------------------------------


def gzip_bytes(data: bytes, level: int = 6) -> bytes:
    return gzip.compress(data, compresslevel=level)


def gunzip_bytes(data: bytes) -> bytes:
    return gzip.decompress(data)


# ---------------------------------------------------------------------------
# Encryption
#
# These are re-exports, not an implementation. AES-256-GCM is defined once, in
# warnetech_envelope; this module previously carried an independent copy, which
# is the duplication pattern that produced the CLI/Worker wire-format break.
# slice_engine.encrypt() imports these names, so they are kept as aliases
# rather than removed.
# ---------------------------------------------------------------------------

from warnetech_envelope import aes_gcm_decrypt, aes_gcm_encrypt  # noqa: E402,F401


# ---------------------------------------------------------------------------
# Parquet (optional, via pyarrow)
# ---------------------------------------------------------------------------


def records_to_parquet_bytes(records: list[dict]) -> bytes:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        import io
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "records_to_parquet_bytes requires 'pyarrow': pip install pyarrow"
        ) from exc

    table = pa.Table.from_pylist(records)
    buf = io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# File IO
# ---------------------------------------------------------------------------


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def atomic_write_bytes(path: str | Path, data: bytes) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(p)
