"""
Warnetech CLI Package
Version 1.0.0

A complete command-line interface for managing Warnetech Integrated Systems
and Security, including signature scoring, learning loops, recovery protocols,
metrics reporting, data slicing, compression, ghost copy creation, and
AI-driven recall.
"""

__version__ = "1.0.0"
__author__ = "Warnetech"
__license__ = "MIT"

from .main import main
from .config import Config
from .logging import setup_logging

__all__ = ["main", "Config", "setup_logging"]
