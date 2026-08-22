"""Integration with AI systems: sending queries to AI controllers,
receiving slice relevance and recall plans, coordinating AI-driven
reconstruction of datasets, and managing AI-assisted defense strategies.

Calls warnetech_ai_controller.controller in-process via direct Python
imports — matching the same wiring philosophy applied to
control_plane_client.py (see docs/WARNETECH-CANONICAL-WIRING-SPEC.txt
decision 1): no network hop, no separate service, one shared process.

This module's public interface (send_query/recall_plan/coordinate_
reconstruction/generate_embedding/assisted_defense_strategy) is unchanged
from the previous warnetech_cli-backed implementation, so routes.py needed
no changes — only what backs these methods moved.
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from .logging import get_logger, log_ai_interaction

logger = get_logger(__name__)


class AIIntegration:
    def __init__(self) -> None:
        try:
            from warnetech_ai_controller import controller
        except ImportError as exc:  # pragma: no cover - repo layout dependent
            raise RuntimeError(
                "warnetech_ai_controller is required for in-process AI wiring; "
                "ensure it is importable alongside warnetech_server"
            ) from exc
        self._controller = controller

    # -- queries --------------------------------------------------------------------

    def send_query(self, query_text: str, slice_embeddings: list[dict]) -> list[dict]:
        from warnetech_ai_controller import embeddings, relevance

        query_embedding = embeddings.generate_slice_embedding({"text": query_text})
        results = relevance.rank_by_similarity(query_embedding, slice_embeddings)
        log_ai_interaction(logger, "query", True, {"query_length": len(query_text), "result_count": len(results)})
        return results

    # -- recall plans -------------------------------------------------------------------

    def recall_plan(self, available_slices: list[dict], total_data_size: int, query_params: Optional[dict] = None) -> dict:
        query = {"available_slices": available_slices, "total_data_size": total_data_size, **(query_params or {})}
        plan = self._controller.plan_recall(query)
        log_ai_interaction(logger, "recall_plan", True, {"selected": plan.get("selected_slice_count", 0)})
        return plan

    # -- reconstruction --------------------------------------------------------------------

    def coordinate_reconstruction(self, selected_slices: list[dict], original_size: int) -> dict:
        plan = self._controller.plan_recall({"available_slices": selected_slices, "total_data_size": original_size})
        quality = plan.get("coverage_ratio") or 0.0

        result = {
            "reconstruction_status": "complete" if quality > 0.9 else "partial",
            "original_size": original_size,
            "reconstructed_size": plan.get("selected_data_size", 0),
            "quality_score": quality * 100,
            "slices_used": plan.get("selected_slice_count", 0),
            "ai_confidence": quality,
            "reconstructed_at": plan.get("planned_at"),
        }
        log_ai_interaction(logger, "reconstruction", True, {"status": result["reconstruction_status"]})
        return result

    def generate_embedding(self, data: bytes, dims: int = 768) -> list[float]:
        from warnetech_ai_controller.config import AIControllerConfig, EmbeddingSettings
        from warnetech_ai_controller.embeddings import generate_slice_embedding

        config = AIControllerConfig(embedding=EmbeddingSettings(dimensions=dims))
        return generate_slice_embedding({"data_sha256": hashlib.sha256(data).hexdigest()}, config)

    # -- AI-assisted defense strategy ------------------------------------------------------

    # -- ghost copy recall ------------------------------------------------------------------

    def ghost_recall_plan(
        self, ghost_copies: list[dict], query_embedding: Optional[list[float]] = None,
        query_params: Optional[dict] = None,
    ) -> dict:
        query = {"ghost_copies": ghost_copies, "query_embedding": query_embedding, **(query_params or {})}
        plan = self._controller.plan_recall_from_ghost(query)
        log_ai_interaction(logger, "ghost_recall_plan", True, {"selected": plan.get("selected_ghost_count", 0)})
        return plan

    def summarize_ghost_copies(self, ghost_list: list[dict]) -> dict:
        summary = self._controller.summarize_ghost_copies(ghost_list)
        log_ai_interaction(logger, "summarize_ghost_copies", True, {"count": summary.get("total_ghost_copies", 0)})
        return summary

    def assisted_defense_strategy(self, available_slices: list[dict], total_data_size: int) -> dict[str, Any]:
        """Combines importance analysis and a recall plan into one
        recommendation, used by routes.post_ai_query() when the caller
        asks for a strategy rather than a raw recall plan.
        """
        importance = self._controller.rank_slices(available_slices)
        plan = self.recall_plan(available_slices, total_data_size)
        recommendation = "proceed" if plan.get("meets_target") else "acquire_more_slices"

        strategy = {
            "importance": importance,
            "recall_plan": plan,
            "recommendation": recommendation,
        }
        log_ai_interaction(logger, "assisted_defense_strategy", True, {"recommendation": recommendation})
        return strategy
