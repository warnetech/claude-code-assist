"""Configuration for the Supabase schema/RPC layer: project URL, anon key,
service role key, and migration settings.

Applying DDL (CREATE TABLE, CREATE FUNCTION) is not possible through
Supabase's PostgREST Data API (`/rest/v1/...`) that the rest of this
system's database.py modules use for row CRUD — that endpoint has no SQL
execution surface. migrations.py instead calls the Supabase Management
API's database query endpoint, which needs a Management API access token
(an organization-level credential from the Supabase dashboard's account
settings) — a different credential from the project's anon/service-role
keys. Anon/service-role keys are still configured here since
utils.py/logging.py may need them for non-DDL bookkeeping, but they cannot
themselves run migrations.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SupabaseCredentials:
    url: str = field(default_factory=lambda: os.environ.get("SUPABASE_URL", ""))
    anon_key: str = field(default_factory=lambda: os.environ.get("SUPABASE_ANON_KEY", ""))
    service_role_key: str = field(default_factory=lambda: os.environ.get("SUPABASE_SERVICE_ROLE_KEY", os.environ.get("SUPABASE_KEY", "")))
    project_ref: str = field(default_factory=lambda: os.environ.get("SUPABASE_PROJECT_REF", ""))
    management_api_token: str = field(default_factory=lambda: os.environ.get("SUPABASE_MANAGEMENT_API_TOKEN", ""))


@dataclass(frozen=True)
class MigrationSettings:
    tables_file: str = "tables.sql"
    rpcs_file: str = "rpcs.sql"
    dry_run: bool = field(default_factory=lambda: os.environ.get("WARNETECH_MIGRATIONS_DRY_RUN", "true").lower() == "true")
    request_timeout_seconds: int = 30
    max_retries: int = 3
    base_retry_delay_seconds: float = 2.0


@dataclass(frozen=True)
class SchemaConfig:
    supabase: SupabaseCredentials = field(default_factory=SupabaseCredentials)
    migration: MigrationSettings = field(default_factory=MigrationSettings)


DEFAULT_CONFIG = SchemaConfig()
