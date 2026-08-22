"""Signature matching, weighting, updates, reinforcement, and cache sync.

The id scheme and reinforcement formulas are ported verbatim from the
Python ``Signature`` dataclass this project's sibling AI-Defense framework
uses, so ids and weights round-trip identically across implementations:

    id         = sig_<attack_type>_<sha1(pattern)[:10]>
    reinforce  = weight = min(max_weight, weight + (max_weight - weight) * rate)   [true positive]
                 weight = max(min_weight, weight - penalty)                        [false positive]
    confidence = clamp(weight * (1 - false_positives / occurrences))
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Optional

from .config import ControlPlaneConfig, DEFAULT_CONFIG
from .database import SupabaseDatabase
from .logging import get_logger
from .state import ControlPlaneState
from .utils import now_iso, sha1_hex

logger = get_logger(__name__)


def signature_id(attack_type: str, pattern: str) -> str:
    return f"sig_{attack_type}_{sha1_hex(pattern)[:10]}"


@dataclass
class Signature:
    id: str
    attack_type: str
    pattern: str
    weight: float = 0.5
    confidence: float = 0.5
    occurrences: int = 0
    false_positives: int = 0
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


class SignatureEngine:
    def __init__(
        self,
        state: ControlPlaneState,
        database: Optional[SupabaseDatabase] = None,
        config: ControlPlaneConfig = DEFAULT_CONFIG,
    ) -> None:
        self._state = state
        self._db = database
        self._config = config

    # -- matching -----------------------------------------------------------

    def match(self, payload: str) -> list[dict]:
        """Returns every cached signature whose pattern matches `payload`,
        each annotated with a `score` equal to its current weight. Pure and
        I/O-free: reads only the in-memory signature cache, so the block
        path never depends on a remote service being reachable.
        """
        matches: list[dict] = []
        for sig in self._state.all_signatures():
            try:
                if re.search(sig["pattern"], payload, re.IGNORECASE):
                    matches.append({**sig, "score": sig.get("weight", 0.5)})
            except re.error:
                logger.warning("invalid signature pattern skipped", signature_id=sig.get("id"))
        matches.sort(key=lambda s: s["score"], reverse=True)
        return matches

    # -- creation / reinforcement --------------------------------------------

    def create(self, attack_type: str, pattern: str) -> Signature:
        sig = Signature(id=signature_id(attack_type, pattern), attack_type=attack_type, pattern=pattern)
        self._state.upsert_signature(sig.to_dict())
        logger.info("signature created", signature_id=sig.id, attack_type=attack_type)
        return sig

    def reinforce(self, sig_id: str, true_positive: bool) -> Optional[dict]:
        sig = self._state.get_signature(sig_id)
        if sig is None:
            logger.warning("reinforce called on unknown signature", signature_id=sig_id)
            return None

        params = self._config.learning
        occurrences = sig.get("occurrences", 0) + 1
        false_positives = sig.get("false_positives", 0)

        if true_positive:
            weight = min(params.max_weight, sig.get("weight", 0.5) + (params.max_weight - sig.get("weight", 0.5)) * params.reinforcement_rate)
        else:
            weight = max(params.min_weight, sig.get("weight", 0.5) - params.penalty)
            false_positives += 1

        confidence = weight * (1 - (false_positives / occurrences)) if occurrences else weight
        confidence = max(params.confidence_floor, min(params.confidence_ceiling, confidence))

        sig.update(
            weight=weight,
            confidence=confidence,
            occurrences=occurrences,
            false_positives=false_positives,
            updated_at=now_iso(),
        )
        self._state.upsert_signature(sig)
        self._state.update_learning(
            sig_id, occurrences=occurrences, false_positives=false_positives,
            true_positives=self._state.get_learning(sig_id).get("true_positives", 0) + (1 if true_positive else 0),
        )
        logger.info("signature reinforced", signature_id=sig_id, weight=weight, confidence=confidence, true_positive=true_positive)
        return sig

    # -- cache sync -----------------------------------------------------------

    def sync_cache(self) -> int:
        """Rebuilds the in-memory cache from Postgres. Called on cold start
        and by the hourly cron; never on the hot scoring path.
        """
        if self._db is None:
            logger.warning("sync_cache called with no database configured")
            return 0
        signatures = self._db.read_signatures(limit=self._config.limits.signature_cache_max)
        self._state.replace_signature_cache(signatures)
        logger.info("signature cache synced", count=len(signatures))
        return len(signatures)
