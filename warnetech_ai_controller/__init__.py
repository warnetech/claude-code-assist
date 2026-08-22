"""Warnetech AI Controller.

The intelligence layer for Warnetech Integrated Systems and Security:
semantic search, slice relevance ranking, reconstruction planning, defense
strategy generation, anomaly classification, test harness analysis, and
external security intelligence integration.

warnetech_server/ai_integration.py calls the functions in `controller`
in-process — see that module for the wiring.

Typical usage::

    from warnetech_ai_controller import controller

    plan = controller.plan_recall({
        "available_slices": slices,
        "total_data_size": 20000,
        "domain": "threats",
    })
    strategy = controller.suggest_defense_strategy(metrics, anomalies)
"""

from . import controller
from .config import AIControllerConfig, DEFAULT_CONFIG
from .logging import get_logger

__version__ = "0.1.0"

__all__ = [
    "controller",
    "AIControllerConfig",
    "DEFAULT_CONFIG",
    "get_logger",
]
