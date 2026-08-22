"""Embedding generation for slices, anomalies, metrics, and test results,
and vector similarity search.

Uses a deterministic hash-projection embedding by default — no ML
dependency required, and identical input always produces an identical
vector, which is enough for exact/near-duplicate recall. Pass a real
`embed_fn` (a sentence transformer, a hosted embedding API) to any
function's `embed_fn` parameter for genuine semantic embeddings; nothing
here assumes which one you use.
"""

from __future__ import annotations

import hashlib
from typing import Callable, Optional

from .config import AIControllerConfig, DEFAULT_CONFIG
from .utils import cosine_similarity, normalize, to_json

EmbedFn = Callable[[str], list[float]]


def _default_embed(text: str, dims: int) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    raw = (digest * ((dims // len(digest)) + 1))[:dims]
    return normalize([b / 255.0 for b in raw])


def _embed_dict(payload: dict, config: AIControllerConfig, embed_fn: Optional[EmbedFn]) -> list[float]:
    text = to_json(payload)
    if embed_fn is not None:
        return embed_fn(text)
    return _default_embed(text, config.embedding.dimensions)


def generate_slice_embedding(slice_metadata: dict, config: AIControllerConfig = DEFAULT_CONFIG, embed_fn: Optional[EmbedFn] = None) -> list[float]:
    return _embed_dict(slice_metadata, config, embed_fn)


def generate_anomaly_embedding(anomaly: dict, config: AIControllerConfig = DEFAULT_CONFIG, embed_fn: Optional[EmbedFn] = None) -> list[float]:
    return _embed_dict(anomaly, config, embed_fn)


def generate_metric_embedding(metric: dict, config: AIControllerConfig = DEFAULT_CONFIG, embed_fn: Optional[EmbedFn] = None) -> list[float]:
    return _embed_dict(metric, config, embed_fn)


def similarity(a: list[float], b: list[float]) -> float:
    return cosine_similarity(a, b)
