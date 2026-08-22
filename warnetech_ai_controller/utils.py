"""Helper functions: JSON handling, vector math, timestamp formatting, and
checksum verification.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any, Iterable


# -- JSON -----------------------------------------------------------------------


def to_json(obj: Any) -> str:
    return json.dumps(obj, default=str, separators=(",", ":"), sort_keys=True)


def from_json(text: str) -> Any:
    return json.loads(text)


# -- vector math --------------------------------------------------------------------


def dot(a: Iterable[float], b: Iterable[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def norm(a: Iterable[float]) -> float:
    return math.sqrt(sum(x * x for x in a)) or 1.0


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return dot(a, b) / (norm(a) * norm(b))


def normalize(vec: list[float]) -> list[float]:
    n = norm(vec)
    return [v / n for v in vec]


# -- timestamps -----------------------------------------------------------------------


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def format_timestamp(epoch_seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch_seconds))


# -- checksums -----------------------------------------------------------------------


def checksum(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def verify_checksum(data: bytes | str, expected: str) -> bool:
    return checksum(data) == expected
