"""Ghost copy creation, storage layout, retrieval, metadata indexing,
embedding generation, and AI-driven recall.

A "ghost copy" is a slice (see slice_engine.Slice) preserved past the point
where its raw data would normally be dropped by retention_engine — the
control plane's answer to "keep a compressed, addressable memory of
everything without paying hot-tier storage cost forever."

Storage layout: ``ghost/{yyyy}/{mm}/{domain}/{slice_id}.bin``

Embeddings default to a deterministic hash-based projection so recall works
with zero external dependencies; pass a real `embed_fn` (e.g. a sentence
transformer or hosted embedding API) for production-quality semantic recall.
"""

from __future__ import annotations

import base64
import hashlib
import math
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .config import ControlPlaneConfig, DEFAULT_CONFIG
from .logging import get_logger
from .slice_engine import Slice
from .utils import now_iso, read_json, sha256_hex, write_json

logger = get_logger(__name__)

EmbedFn = Callable[[str], list[float]]


def _default_embed(text: str, dims: int = 32) -> list[float]:
    """A cheap, deterministic, dependency-free embedding: hashes the text
    into `dims` floats. Preserves near-duplicate detection (identical text
    -> identical vector) but has none of the semantic properties of a real
    embedding model — swap it out via `embed_fn` for anything beyond exact
    or near-exact recall.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    # Repeat the digest to cover `dims` floats, then normalize to unit length.
    raw = (digest * ((dims // len(digest)) + 1))[:dims]
    vec = [b / 255.0 for b in raw]
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (norm_a * norm_b)


@dataclass
class GhostIndexEntry:
    slice_id: str
    domain: str
    path: str
    embedding: list[float]
    summary: str
    indexed_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


class GhostEngine:
    def __init__(self, config: ControlPlaneConfig = DEFAULT_CONFIG, embed_fn: Optional[EmbedFn] = None) -> None:
        self._config = config
        self._embed_fn = embed_fn or _default_embed
        self._base_dir = Path(config.local_backup_dir) / "ghost"
        self._index_path = self._base_dir / "index.json"

    # -- storage layout --------------------------------------------------------

    def _path_for(self, slice_obj: Slice) -> Path:
        created = slice_obj.metadata.created_at  # "2026-08-05T13:11:17Z"
        year, month = created[0:4], created[5:7]
        return self._base_dir / year / month / slice_obj.metadata.domain / f"{slice_obj.metadata.slice_id}.bin"

    # -- create / retrieve --------------------------------------------------------

    def create_ghost_copy(self, slice_obj: Slice, summary: str) -> GhostIndexEntry:
        path = self._path_for(slice_obj)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(slice_obj.body)

        embedding = self._embed_fn(summary)
        entry = GhostIndexEntry(
            slice_id=slice_obj.metadata.slice_id,
            domain=slice_obj.metadata.domain,
            path=str(path),
            embedding=embedding,
            summary=summary,
        )
        self._append_index(entry)
        logger.info("ghost copy created", slice_id=entry.slice_id, path=entry.path)
        return entry

    def retrieve_ghost_copy(self, slice_id: str) -> Optional[bytes]:
        entry = self._find_index_entry(slice_id)
        if entry is None:
            return None
        path = Path(entry["path"])
        if not path.exists():
            logger.error("ghost copy indexed but missing on disk", slice_id=slice_id, path=str(path))
            return None
        return path.read_bytes()

    # -- metadata index -----------------------------------------------------------

    def _load_index(self) -> list[dict]:
        if not self._index_path.exists():
            return []
        return read_json(self._index_path)

    def _append_index(self, entry: GhostIndexEntry) -> None:
        index = self._load_index()
        index.append(entry.to_dict())
        write_json(self._index_path, index)

    def _find_index_entry(self, slice_id: str) -> Optional[dict]:
        for entry in self._load_index():
            if entry["slice_id"] == slice_id:
                return entry
        return None

    # -- embeddings / recall --------------------------------------------------------

    def generate_embedding(self, text: str) -> list[float]:
        return self._embed_fn(text)

    def ai_recall(self, query: str, top_k: int = 5) -> list[dict]:
        """Naive cosine-similarity search over the ghost index. Fine for the
        index sizes this control plane expects (ghost tier is aggregates,
        not raw events); swap for a vector index if that assumption changes.
        """
        query_vec = self._embed_fn(query)
        scored = [
            {**entry, "similarity": _cosine_similarity(query_vec, entry["embedding"])}
            for entry in self._load_index()
        ]
        scored.sort(key=lambda e: e["similarity"], reverse=True)
        return scored[:top_k]


# ---------------------------------------------------------------------------
# Ghost copy engine, take two: a flat, storage-format-agnostic record used by
# warnetech_server's /ghost/create and /ghost/recall routes.
#
# GhostIndexEntry/GhostEngine above stay untouched (existing embedding-recall
# behavior, existing on-disk layout) — this section is additive, not a
# replacement. It operates on its own index/blob files so the two schemes
# never collide on disk.
# ---------------------------------------------------------------------------


@dataclass
class GhostRecord:
    id: str
    time_range: dict
    system: str
    type: str
    size: int
    checksum: str
    compression_type: str
    encryption_key_id: Optional[str]
    metadata: dict
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


def _records_base_dir(config: ControlPlaneConfig) -> Path:
    return Path(config.local_backup_dir) / "ghost"


def _records_index_path(config: ControlPlaneConfig) -> Path:
    return _records_base_dir(config) / "records_index.json"


def _blob_path(ghost_id: str, config: ControlPlaneConfig) -> Path:
    return _records_base_dir(config) / "blobs" / f"{ghost_id}.bin"


def _load_records_index(config: ControlPlaneConfig) -> list[dict]:
    path = _records_index_path(config)
    if not path.exists():
        return []
    return read_json(path)


def _slice_metadata_dict(slice_metadata: Any) -> dict:
    """Accepts either a plain dict or a slice_engine.SliceMetadata-shaped
    object (anything with a to_dict()) so callers can pass either straight
    through.
    """
    if hasattr(slice_metadata, "to_dict"):
        return slice_metadata.to_dict()
    return dict(slice_metadata)


def create_ghost_copy(
    slice_metadata: Any,
    compressed_payload: bytes,
    config: ControlPlaneConfig = DEFAULT_CONFIG,
    encryption_key_id: Optional[str] = None,
    ghost_type: str = "slice",
    embed_fn: Optional[EmbedFn] = None,
) -> GhostRecord:
    """Builds a GhostRecord for `compressed_payload` and writes the payload
    to the ghost blob store, keyed by the newly minted ghost id.

    Does not touch the metadata index — that is store_ghost_copy()'s job, so
    a caller can build several candidate records before committing any of
    them.
    """
    meta = _slice_metadata_dict(slice_metadata)
    ghost_id = str(uuid.uuid4())

    blob_path = _blob_path(ghost_id, config)
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(compressed_payload)

    embed = embed_fn or _default_embed
    embedding = embed(sha256_hex(compressed_payload))

    record = GhostRecord(
        id=ghost_id,
        time_range={"start": meta.get("time_start"), "end": meta.get("time_end")},
        system=meta.get("domain", "unknown"),
        type=ghost_type,
        size=len(compressed_payload),
        checksum=sha256_hex(compressed_payload),
        compression_type=config.compression.algorithm,
        encryption_key_id=encryption_key_id,
        metadata={**meta, "embedding": embedding},
    )
    logger.info("ghost record created", ghost_id=ghost_id, system=record.system, size=record.size)
    return record


def store_ghost_copy(ghost_record: GhostRecord | dict, config: ControlPlaneConfig = DEFAULT_CONFIG) -> bool:
    """Persists a GhostRecord to the local metadata index. Idempotent on
    `id` — storing the same record twice replaces the earlier entry rather
    than duplicating it.
    """
    record_dict = ghost_record.to_dict() if isinstance(ghost_record, GhostRecord) else dict(ghost_record)
    index = _load_records_index(config)
    index = [r for r in index if r.get("id") != record_dict.get("id")]
    index.append(record_dict)

    try:
        write_json(_records_index_path(config), index)
    except OSError as exc:
        logger.error("failed to store ghost record", ghost_id=record_dict.get("id"), error=str(exc))
        return False

    logger.info("ghost record stored", ghost_id=record_dict.get("id"))
    return True


def list_ghost_copies(filter_params: Optional[dict] = None, config: ControlPlaneConfig = DEFAULT_CONFIG) -> list[dict]:
    """Filters the ghost record index by exact match on `system`/`type`, and
    by time-range overlap when `filter_params` carries `time_start`/
    `time_end`. An empty/None filter returns every record.
    """
    filter_params = filter_params or {}
    records = _load_records_index(config)

    system = filter_params.get("system")
    ghost_type = filter_params.get("type")
    f_start = filter_params.get("time_start")
    f_end = filter_params.get("time_end")

    matched = []
    for record in records:
        if system is not None and record.get("system") != system:
            continue
        if ghost_type is not None and record.get("type") != ghost_type:
            continue
        if f_start and f_end:
            r_range = record.get("time_range") or {}
            r_start, r_end = r_range.get("start"), r_range.get("end")
            if r_start and r_end and (r_end < f_start or r_start > f_end):
                continue
        matched.append(record)
    return matched


def fetch_ghost_copy(ghost_id: str, config: ControlPlaneConfig = DEFAULT_CONFIG) -> Optional[dict]:
    """Returns the stored record plus its payload (base64-encoded, so the
    result is directly JSON-serializable for warnetech_server's HTTP
    response), or None if the id is unknown or the blob is missing.
    """
    record = next((r for r in _load_records_index(config) if r.get("id") == ghost_id), None)
    if record is None:
        logger.warning("ghost copy not found", ghost_id=ghost_id)
        return None

    blob_path = _blob_path(ghost_id, config)
    if not blob_path.exists():
        logger.error("ghost record indexed but blob missing on disk", ghost_id=ghost_id, path=str(blob_path))
        return None

    payload = blob_path.read_bytes()
    return {
        "record": record,
        "payload_b64": base64.b64encode(payload).decode("ascii"),
    }


def verify_ghost_integrity(ghost_id: str, config: ControlPlaneConfig = DEFAULT_CONFIG) -> dict:
    """Recomputes the payload's checksum and compares it against the
    checksum recorded at creation time. Fails soft: a missing record or
    blob is reported as `valid: False` with a `reason`, never an exception.
    """
    fetched = fetch_ghost_copy(ghost_id, config)
    if fetched is None:
        return {"ghost_id": ghost_id, "valid": False, "reason": "not_found"}

    payload = base64.b64decode(fetched["payload_b64"])
    expected = fetched["record"].get("checksum")
    actual = sha256_hex(payload)
    valid = actual == expected

    if not valid:
        logger.error("ghost integrity check failed", ghost_id=ghost_id, expected=expected, actual=actual)

    return {
        "ghost_id": ghost_id,
        "valid": valid,
        "expected_checksum": expected,
        "actual_checksum": actual,
    }
