"""Supabase schema and RPC layer for Warnetech.

Ships tables.sql and rpcs.sql as the source of truth, and migrations.py to
apply them via the Supabase Management API (the project's anon/service-role
keys cannot execute DDL — only migrations.py's Management API token can).

Defaults to a dry run — see migrations.py's module docstring for why, and
tables.sql / rpcs.sql for the specific conflicts with what is already live
in tewartech-project-supabase that made that default necessary.
"""

from .config import SchemaConfig, DEFAULT_CONFIG
from .logging import get_logger
from .migrations import apply_file, apply_schema

__version__ = "0.1.0"

__all__ = [
    "SchemaConfig",
    "DEFAULT_CONFIG",
    "get_logger",
    "apply_file",
    "apply_schema",
]
