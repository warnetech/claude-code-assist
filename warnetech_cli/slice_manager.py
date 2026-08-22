"""
Data Slicing Management Module
Implements time-based and domain-based data slicing with metadata generation.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List


class SliceManager:
    """Manages data slicing across time and domain dimensions."""

    SLICE_WINDOWS = {
        "5min": timedelta(minutes=5),
        "1hour": timedelta(hours=1),
        "1day": timedelta(days=1),
    }

    DOMAIN_TYPES = ["system", "tenant", "attack_type"]

    @staticmethod
    def create_time_slice(
        data: bytes, window_size: str = "1hour"
    ) -> Dict[str, Any]:
        """
        Create time-based data slice.

        Args:
            data: Data to slice
            window_size: Slice window (5min, 1hour, 1day)

        Returns:
            Slice metadata and data reference
        """
        now = datetime.utcnow()
        window = SliceManager.SLICE_WINDOWS.get(window_size, timedelta(hours=1))

        slice_start = now - (now - datetime.min) % window
        slice_end = slice_start + window

        return {
            "slice_type": "time",
            "window": window_size,
            "start_time": slice_start.isoformat(),
            "end_time": slice_end.isoformat(),
            "size_bytes": len(data),
            "created_at": now.isoformat(),
        }

    @staticmethod
    def create_domain_slice(
        data: bytes, domain_type: str, domain_value: str
    ) -> Dict[str, Any]:
        """
        Create domain-based data slice.

        Args:
            data: Data to slice
            domain_type: Type of domain (system, tenant, attack_type)
            domain_value: Domain value

        Returns:
            Slice metadata
        """
        if domain_type not in SliceManager.DOMAIN_TYPES:
            raise ValueError(f"Invalid domain type: {domain_type}")

        now = datetime.utcnow()

        return {
            "slice_type": "domain",
            "domain_type": domain_type,
            "domain_value": domain_value,
            "size_bytes": len(data),
            "created_at": now.isoformat(),
        }

    @staticmethod
    def normalize_slice(slice_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize slice metadata for storage.

        Args:
            slice_metadata: Raw slice metadata

        Returns:
            Normalized metadata
        """
        normalized = {
            "slice_id": f"{slice_metadata.get('slice_type')}_{datetime.utcnow().timestamp()}",
            "slice_type": slice_metadata.get("slice_type"),
            "size_bytes": slice_metadata.get("size_bytes", 0),
            "created_at": slice_metadata.get("created_at"),
            "normalized_at": datetime.utcnow().isoformat(),
        }

        if slice_metadata.get("slice_type") == "time":
            normalized.update({
                "window": slice_metadata.get("window"),
                "start_time": slice_metadata.get("start_time"),
                "end_time": slice_metadata.get("end_time"),
            })
        elif slice_metadata.get("slice_type") == "domain":
            normalized.update({
                "domain_type": slice_metadata.get("domain_type"),
                "domain_value": slice_metadata.get("domain_value"),
            })

        return normalized

    @staticmethod
    def merge_slices(slices: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge multiple slices into unified metadata.

        Args:
            slices: List of slice metadata

        Returns:
            Merged slice information
        """
        total_size = sum(s.get("size_bytes", 0) for s in slices)
        earliest = min((s.get("created_at") for s in slices), default=None)

        return {
            "merged_slice_id": f"merged_{datetime.utcnow().timestamp()}",
            "slice_count": len(slices),
            "total_size_bytes": total_size,
            "earliest_slice": earliest,
            "merged_at": datetime.utcnow().isoformat(),
            "slices": slices,
        }

    @staticmethod
    def get_slice_coverage(
        slices: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Analyze coverage of slices.

        Args:
            slices: List of slices

        Returns:
            Coverage analysis
        """
        if not slices:
            return {"coverage_percent": 0, "slice_count": 0}

        total_size = sum(s.get("size_bytes", 0) for s in slices)
        slice_count = len(slices)

        coverage = {
            "total_size_bytes": total_size,
            "slice_count": slice_count,
            "avg_slice_size": total_size / slice_count if slice_count > 0 else 0,
            "coverage_percent": 100 if total_size > 0 else 0,
        }

        time_slices = [s for s in slices if s.get("slice_type") == "time"]
        domain_slices = [s for s in slices if s.get("slice_type") == "domain"]

        coverage["time_slices"] = len(time_slices)
        coverage["domain_slices"] = len(domain_slices)

        return coverage

    @staticmethod
    def plan_slicing_strategy(
        data_size_bytes: int, target_slice_size: int = 1024 * 1024
    ) -> Dict[str, Any]:
        """
        Plan slicing strategy based on data size.

        Args:
            data_size_bytes: Total data size
            target_slice_size: Target size per slice

        Returns:
            Recommended slicing strategy
        """
        estimated_slices = max(1, data_size_bytes // target_slice_size)

        return {
            "total_data_size": data_size_bytes,
            "target_slice_size": target_slice_size,
            "estimated_slice_count": estimated_slices,
            "avg_slice_size": data_size_bytes // estimated_slices if estimated_slices > 0 else data_size_bytes,
            "recommended_window": "1hour" if estimated_slices > 100 else "1day",
        }
