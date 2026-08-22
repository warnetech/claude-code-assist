"""
Data Retention Management Module
Implements three-tier retention policies (Hot, Warm, Ghost) with automatic tier promotion.
"""

from datetime import datetime
from typing import Dict, Any, List


class RetentionPolicy:
    """Manages data retention across three tiers."""

    TIER_CONFIG = {
        "hot": {
            "max_age_days": 3,
            "compression": "lz4",
            "location": "hot_storage",
            "ai_enabled": True,
        },
        "warm": {
            "max_age_days": 30,
            "compression": "zstd-medium",
            "location": "warm_storage",
            "ai_enabled": True,
        },
        "ghost": {
            "max_age_days": 365,
            "compression": "zstd-max",
            "location": "ghost_archive",
            "ai_enabled": True,
        },
    }

    @staticmethod
    def get_tier_for_age(age_days: float) -> str:
        """
        Determine which tier data should be in based on age.

        Args:
            age_days: Age of data in days

        Returns:
            Tier name (hot, warm, or ghost)
        """
        if age_days <= RetentionPolicy.TIER_CONFIG["hot"]["max_age_days"]:
            return "hot"
        elif age_days <= RetentionPolicy.TIER_CONFIG["warm"]["max_age_days"]:
            return "warm"
        else:
            return "ghost"

    @staticmethod
    def should_promote(current_tier: str, age_days: float) -> bool:
        """
        Check if data should be promoted to next tier.

        Args:
            current_tier: Current tier name
            age_days: Age of data in days

        Returns:
            True if promotion recommended
        """
        target_tier = RetentionPolicy.get_tier_for_age(age_days)
        tier_order = ["hot", "warm", "ghost"]
        return tier_order.index(target_tier) > tier_order.index(current_tier)

    @staticmethod
    def should_expire(age_days: float) -> bool:
        """
        Check if data has exceeded maximum retention.

        Args:
            age_days: Age of data in days

        Returns:
            True if data should be expired
        """
        max_ghost_age = RetentionPolicy.TIER_CONFIG["ghost"]["max_age_days"]
        return age_days > max_ghost_age

    @staticmethod
    def get_compression_for_tier(tier: str) -> str:
        """
        Get compression method for tier.

        Args:
            tier: Tier name

        Returns:
            Compression method
        """
        return RetentionPolicy.TIER_CONFIG[tier]["compression"]

    @staticmethod
    def calculate_tier_stats(records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate statistics across tiers.

        Args:
            records: List of data records with timestamps

        Returns:
            Stats by tier
        """
        now = datetime.utcnow()
        stats = {"hot": 0, "warm": 0, "ghost": 0, "expired": 0}

        for record in records:
            timestamp = datetime.fromisoformat(record.get("timestamp", ""))
            age = (now - timestamp).days
            tier = RetentionPolicy.get_tier_for_age(age)
            if RetentionPolicy.should_expire(age):
                stats["expired"] += 1
            else:
                stats[tier] += 1

        return stats

    @staticmethod
    def create_retention_plan(
        records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Create plan for tier promotion and expiration.

        Args:
            records: List of data records

        Returns:
            Promotion and expiration plan
        """
        now = datetime.utcnow()
        plan = {
            "promote_to_warm": [],
            "promote_to_ghost": [],
            "expire": [],
            "timestamp": now.isoformat(),
        }

        for record in records:
            record_id = record.get("id")
            timestamp = datetime.fromisoformat(record.get("timestamp", ""))
            age = (now - timestamp).days
            current_tier = record.get("tier", "hot")

            if RetentionPolicy.should_expire(age):
                plan["expire"].append(record_id)
            elif current_tier == "hot" and age > 3:
                plan["promote_to_warm"].append(record_id)
            elif current_tier == "warm" and age > 30:
                plan["promote_to_ghost"].append(record_id)

        return plan
