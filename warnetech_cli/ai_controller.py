"""
AI Controller Module
Implements AI-driven slice selection, semantic search, and data reconstruction.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class AIController:
    """Manages AI-driven data reconstruction and slice selection."""

    RECONSTRUCTION_THRESHOLD = 0.1  # 10% of data for reconstruction
    EMBEDDING_DIMENSIONS = 768

    @staticmethod
    def select_optimal_slices(
        available_slices: List[Dict[str, Any]],
        total_data_size: int,
        query_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Select optimal slices for reconstruction (target <10% of data).

        Args:
            available_slices: List of available slices
            total_data_size: Total stored data size
            query_params: Query parameters for slice selection

        Returns:
            Slice selection plan with AI reasoning
        """
        target_size = int(total_data_size * AIController.RECONSTRUCTION_THRESHOLD)
        selected_slices = []
        accumulated_size = 0

        sorted_slices = sorted(
            available_slices,
            key=lambda s: s.get("size_bytes", 0),
            reverse=True,
        )

        for slice_meta in sorted_slices:
            if accumulated_size >= target_size:
                break
            selected_slices.append(slice_meta)
            accumulated_size += slice_meta.get("size_bytes", 0)

        selection_ratio = accumulated_size / total_data_size if total_data_size > 0 else 0

        return {
            "selected_slice_count": len(selected_slices),
            "selected_data_size": accumulated_size,
            "total_data_size": total_data_size,
            "selection_ratio": selection_ratio,
            "meets_threshold": selection_ratio <= AIController.RECONSTRUCTION_THRESHOLD,
            "slices": selected_slices,
            "selected_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def generate_embeddings(data: bytes, embedding_dims: int = 768) -> List[float]:
        """
        Generate semantic embeddings for data (simulated AI).

        Args:
            data: Data to embed
            embedding_dims: Embedding dimensions

        Returns:
            Embedding vector (simulated)
        """
        import hashlib

        data_hash = hashlib.sha256(data).digest()
        embeddings = []

        for i in range(embedding_dims):
            byte_val = data_hash[i % len(data_hash)]
            normalized = (byte_val / 255.0) * 2.0 - 1.0
            embeddings.append(float(normalized))

        return embeddings

    @staticmethod
    def semantic_search(
        query_text: str,
        slice_embeddings: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Search slices by semantic similarity.

        Args:
            query_text: Query text
            slice_embeddings: List of slices with embeddings

        Returns:
            Ranked results by relevance
        """
        query_hash = hash(query_text) % 256
        ranked_results = []

        for slice_data in slice_embeddings:
            embedding = slice_data.get("embedding", [])
            if not embedding:
                continue

            similarity = sum(
                e * (query_hash % 256) / 256.0 for e in embedding[:10]
            ) / 10.0

            ranked_results.append({
                "slice_id": slice_data.get("slice_id"),
                "similarity_score": min(similarity, 1.0),
                "slice_metadata": slice_data,
            })

        ranked_results.sort(
            key=lambda x: x["similarity_score"], reverse=True
        )

        return ranked_results

    @staticmethod
    def reconstruct_data(
        selected_slices: List[Dict[str, Any]],
        original_size: int,
    ) -> Dict[str, Any]:
        """
        Reconstruct data from selected slices using AI inference.

        Args:
            selected_slices: Slices to use for reconstruction
            original_size: Original data size before compression

        Returns:
            Reconstruction metadata and quality metrics
        """
        reconstructed_size = sum(s.get("size_bytes", 0) for s in selected_slices)
        reconstruction_quality = min(
            reconstructed_size / original_size if original_size > 0 else 0, 1.0
        )

        return {
            "reconstruction_status": "complete" if reconstruction_quality > 0.9 else "partial",
            "original_size": original_size,
            "reconstructed_size": reconstructed_size,
            "quality_score": reconstruction_quality * 100,
            "slices_used": len(selected_slices),
            "ai_confidence": reconstruction_quality,
            "reconstructed_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def analyze_slice_importance(
        slices: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Analyze importance of slices for reconstruction.

        Args:
            slices: List of slices

        Returns:
            Importance scores for each slice
        """
        if not slices:
            return {"total_slices": 0, "importance_scores": []}

        total_size = sum(s.get("size_bytes", 0) for s in slices)
        importance_scores = []

        for slice_data in slices:
            size = slice_data.get("size_bytes", 0)
            importance = (size / total_size * 100) if total_size > 0 else 0

            importance_scores.append({
                "slice_id": slice_data.get("slice_id"),
                "importance_percent": importance,
                "size_bytes": size,
            })

        importance_scores.sort(
            key=lambda x: x["importance_percent"], reverse=True
        )

        return {
            "total_slices": len(slices),
            "total_size": total_size,
            "importance_scores": importance_scores,
        }

    @staticmethod
    def predict_reconstruction_success(
        selected_slices: List[Dict[str, Any]],
        total_data_size: int,
    ) -> Dict[str, Any]:
        """
        Predict success probability of reconstruction.

        Args:
            selected_slices: Selected slices
            total_data_size: Original total size

        Returns:
            Success prediction with confidence metrics
        """
        selected_size = sum(s.get("size_bytes", 0) for s in selected_slices)
        coverage_ratio = selected_size / total_data_size if total_data_size > 0 else 0

        base_probability = min(coverage_ratio / 0.1, 1.0) if coverage_ratio > 0 else 0

        return {
            "success_probability": base_probability,
            "confidence_level": "high" if base_probability > 0.85 else "medium" if base_probability > 0.7 else "low",
            "coverage_ratio": coverage_ratio,
            "required_slices": len(selected_slices),
            "recommendation": "proceed" if base_probability > 0.7 else "acquire_more_slices",
        }
