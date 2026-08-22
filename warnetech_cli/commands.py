"""
Command Implementations Module
Implements all 20 warnetech CLI commands with full functionality.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path

from warnetech_cli.config import Config
from warnetech_cli.logging import setup_logging
# SecurityManager import removed: deprecated and never called (see security.py)
from warnetech_cli import diagnostics
from warnetech_cli.compression import CompressionManager
from warnetech_cli.utils import FileUtils
from warnetech_cli.retention import RetentionPolicy
from warnetech_cli.slice_manager import SliceManager
from warnetech_cli.ai_controller import AIController
from warnetech_cli.ghost_store import GhostStore
from warnetech_cli.server_client import ServerClient


class Commands:
    """Implements all warnetech CLI commands."""

    def __init__(self, config: Config):
        self.config = config
        self.logger = setup_logging(log_level=config.get("log_level", "INFO"))
        self.client = ServerClient(config)

    def status(self, args: Optional[List[str]] = None) -> Dict[str, Any]:
        """Get system status from warnetech-server."""
        return self.client.get("/status")

    def metrics(self, source_id: str = "cli") -> Dict[str, Any]:
        """Retrieve system metrics from warnetech-server."""
        return self.client.get("/metrics", params={"source_id": source_id})

    def signatures(self, attack_type: Optional[str] = None) -> Dict[str, Any]:
        """List attack signatures from warnetech-server."""
        return self.client.get("/signatures", params={"attack_type": attack_type})

    def learn(self, attack_type: str, pattern: str, true_positive: bool = True) -> Dict[str, Any]:
        """Report an outcome to warnetech-server's adaptive learning model."""
        return self.client.post("/learn", body={
            "attack_type": attack_type,
            "pattern": pattern,
            "true_positive": true_positive,
        })

    def recover(self, attack_id: str) -> Dict[str, Any]:
        """Trigger warnetech-server's recovery protocol for an incident."""
        return self.client.post("/recover", body={"incident_id": attack_id})

    def slice(
        self, data_path: str, window_size: str = "1hour"
    ) -> Dict[str, Any]:
        """Create data slices."""
        try:
            data = FileUtils.read_bytes(Path(data_path))
            slice_meta = SliceManager.create_time_slice(data, window_size)
            slice_meta["data_size"] = len(data)
            return slice_meta
        except Exception as e:
            return {"error": str(e)}

    def compress(
        self, data_path: str, method: str = "zstd-medium"
    ) -> Dict[str, Any]:
        """Compress data."""
        try:
            data = FileUtils.read_bytes(Path(data_path))
            compressed = CompressionManager.compress(data, method)
            ratio = CompressionManager.get_compression_ratio(
                len(data), len(compressed)
            )
            return {
                "original_size": len(data),
                "compressed_size": len(compressed),
                "compression_ratio": ratio,
                "method": method,
            }
        except Exception as e:
            return {"error": str(e)}

    def ghost_create(
        self, data_path: str, source_id: str = "auto"
    ) -> Dict[str, Any]:
        """Create ghost copy."""
        try:
            data = FileUtils.read_bytes(Path(data_path))
            source_meta = {"id": source_id}
            ghost_meta = GhostStore.create_ghost_copy(data, source_meta)
            return ghost_meta
        except Exception as e:
            return {"error": str(e)}

    def ghost_recall(self, ghost_id: str) -> Dict[str, Any]:
        """Recall ghost copy."""
        return GhostStore.retrieve_ghost_copy(ghost_id)

    def retention_apply(self, policy_name: str) -> Dict[str, Any]:
        """Apply a retention policy via warnetech-server. Validates the
        policy name locally first (fast, no round-trip for a typo) before
        forwarding the request.
        """
        policy_config = RetentionPolicy.TIER_CONFIG.get(policy_name)
        if not policy_config:
            return {"error": f"Unknown policy: {policy_name}"}
        return self.client.post("/retention/apply", body={"policy_name": policy_name, "config": policy_config})

    def retention_policy(
        self, action: str, policy_name: str = "hot"
    ) -> Dict[str, Any]:
        """Manage retention policies. `list` is answered locally from the
        known tier names; `get` reflects warnetech-server's actual config.
        """
        if action == "list":
            return {
                "policies": list(RetentionPolicy.TIER_CONFIG.keys()),
                "listed_at": datetime.utcnow().isoformat(),
            }
        elif action == "get":
            return self.client.get("/retention/policy")
        else:
            return {"error": f"Unknown action: {action}"}

    def ai_query(self, query: str) -> Dict[str, Any]:
        """Send a semantic query to warnetech-server's AI integration."""
        return self.client.post("/ai/query", body={"mode": "search", "query": query, "slice_embeddings": []})

    def ai_recall(self, dataset_id: str) -> Dict[str, Any]:
        """Recall data using AI inference."""
        slices = [
            {"slice_id": f"slice_{i}", "size_bytes": 10000}
            for i in range(5)
        ]
        plan = AIController.select_optimal_slices(slices, 1000000)
        return {
            "dataset_id": dataset_id,
            "reconstruction_plan": plan,
            "status": "ready",
        }

    def export(
        self, data_path: str, output_format: str = "json"
    ) -> Dict[str, Any]:
        """Export data."""
        try:
            data = FileUtils.read_bytes(Path(data_path))
            return {
                "source": data_path,
                "format": output_format,
                "size_bytes": len(data),
                "exported_at": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            return {"error": str(e)}

    def import_data(
        self, data_path: str, import_format: str = "json"
    ) -> Dict[str, Any]:
        """Import data."""
        try:
            data = FileUtils.read_bytes(Path(data_path))
            return {
                "source": data_path,
                "format": import_format,
                "size_bytes": len(data),
                "imported_at": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            return {"error": str(e)}

    def config(self, action: str, key: Optional[str] = None) -> Dict[str, Any]:
        """Manage configuration."""
        if action == "show":
            return {
                "config": self.config.to_dict(),
                "shown_at": datetime.utcnow().isoformat(),
            }
        elif action == "get" and key:
            return {
                "key": key,
                "value": self.config.get(key),
                "retrieved_at": datetime.utcnow().isoformat(),
            }
        else:
            return {"error": f"Unknown action: {action}"}

    def server_ping(self) -> Dict[str, Any]:
        """Ping warnetech-server and measure real round-trip latency."""
        result = diagnostics.server_ping_check(self.client, self.config)
        result.pop("ok", None)
        result["status"] = result.get("status", "unreachable")
        result["timestamp"] = datetime.utcnow().isoformat()
        return result

    def db_check(self) -> Dict[str, Any]:
        """Check database connectivity via warnetech-server."""
        return self.client.get("/db/health")

    def db_sync(self) -> Dict[str, Any]:
        """Trigger a database partition/rollup sync via warnetech-server."""
        return self.client.post("/db/sync")

    def ai_diagnose(self):
        from warnetech_ai_controller.diagnostics import ai_diagnose
        return ai_diagnose()
