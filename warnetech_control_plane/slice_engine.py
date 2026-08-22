"""Data slicing: time slicing, domain slicing, normalization, compression,
encryption, metadata generation, and Parquet conversion.

A "slice" is the unit ghost_engine stores: a bounded, self-describing chunk
of records plus a metadata envelope (hash, count, time range) that lets
retrieval verify integrity without re-reading the whole slice.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from .config import ControlPlaneConfig, DEFAULT_CONFIG
from .utils import (
    aes_gcm_encrypt,
    gzip_bytes,
    now_iso,
    records_to_parquet_bytes,
    sha256_hex,
    to_ndjson,
)


@dataclass
class SliceMetadata:
    slice_id: str
    domain: str
    time_start: str
    time_end: str
    record_count: int
    sha256: str
    compressed: bool
    encrypted: bool
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Slice:
    metadata: SliceMetadata
    body: bytes
    nonce: Optional[bytes] = None


class SliceEngine:
    def __init__(self, config: ControlPlaneConfig = DEFAULT_CONFIG) -> None:
        self._config = config

    # -- slicing --------------------------------------------------------------

    def time_slice(self, records: list[dict], start: str, end: str, timestamp_key: str = "timestamp") -> list[dict]:
        return [r for r in records if start <= r.get(timestamp_key, "") < end]

    def domain_slice(self, records: list[dict], domain_key: str, domain_value: str) -> list[dict]:
        return [r for r in records if r.get(domain_key) == domain_value]

    # -- normalization --------------------------------------------------------

    def normalize(self, records: list[dict]) -> list[dict]:
        """Sorts keys and drops None values so identical logical records
        hash identically regardless of insertion order.
        """
        return [{k: v for k, v in sorted(r.items()) if v is not None} for r in records]

    # -- compression / encryption -----------------------------------------------

    def compress(self, data: bytes) -> bytes:
        return gzip_bytes(data, level=self._config.compression.level)

    def encrypt(self, data: bytes, key: bytes) -> tuple[bytes, bytes]:
        return aes_gcm_encrypt(key, data)

    # -- Parquet ----------------------------------------------------------------

    def to_parquet(self, records: list[dict]) -> bytes:
        return records_to_parquet_bytes(records)

    # -- metadata + assembly ------------------------------------------------------

    def generate_metadata(
        self, slice_id: str, domain: str, records: list[dict], body: bytes,
        time_start: str, time_end: str, compressed: bool, encrypted: bool,
    ) -> SliceMetadata:
        return SliceMetadata(
            slice_id=slice_id,
            domain=domain,
            time_start=time_start,
            time_end=time_end,
            record_count=len(records),
            sha256=sha256_hex(body),
            compressed=compressed,
            encrypted=encrypted,
        )

    def build_slice(
        self, slice_id: str, domain: str, records: list[dict],
        time_start: str, time_end: str,
        compress: bool = True, encryption_key: Optional[bytes] = None,
    ) -> Slice:
        normalized = self.normalize(records)
        body = to_ndjson(normalized).encode("utf-8")

        if compress:
            body = self.compress(body)

        nonce = None
        if encryption_key is not None:
            nonce, body = self.encrypt(body, encryption_key)

        metadata = self.generate_metadata(
            slice_id, domain, records, body, time_start, time_end,
            compressed=compress, encrypted=encryption_key is not None,
        )
        return Slice(metadata=metadata, body=body, nonce=nonce)
