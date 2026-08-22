"""Applies tables.sql and rpcs.sql to the existing Supabase project.

Four safety properties, all load-bearing given this project already has
live data and live callers:

1. Table statements use CREATE TABLE IF NOT EXISTS, so no existing table's
   columns are ever altered or dropped by this module — see tables.sql's
   header comment for the specific conflict this guards against.

2. `dry_run` defaults to True (config.MigrationSettings.dry_run). A dry
   run logs every statement it *would* execute and returns without
   calling Supabase at all. Set WARNETECH_MIGRATIONS_DRY_RUN=false (or
   pass dry_run=False explicitly) only after confirming rpcs.sql's
   `create or replace function` statements — unlike the tables, those DO
   overwrite live behavior; see rpcs.sql's header comment.

3. Every `create or replace function` in rpcs.sql must name a function in
   SAFE_RPC_FUNCTIONS below. This is the actual enforcement of "only the
   approved RPCs" — a new function added to rpcs.sql without also being
   added to this set is refused rather than silently applied, so scope
   creep in the SQL file can't slip past review.

4. Functions named in CREATE_ONLY_IF_MISSING below are applied only when
   pg_proc has no matching function yet — a live deployment (with its own
   accumulated behavior, e.g. partition-creation logging) is never
   silently replaced by whatever this file currently defines. This check
   only runs when dry_run is False, since dry_run promises "no calls to
   Supabase at all."
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import SchemaConfig, DEFAULT_CONFIG
from .logging import get_logger, log_migration_step
from .utils import SqlExecutionError, execute_sql_with_retry, split_statements

logger = get_logger(__name__)

_SCHEMA_DIR = Path(__file__).resolve().parent

# The complete set of RPC functions this module is authorized to create or
# replace. Every name here has been individually approved for live
# application against tewartech-project-supabase.
SAFE_RPC_FUNCTIONS = frozenset({
    "maintain_partitions",
    "refresh_metric_rollups",
    "maintain_threat_event_partitions",
})

# Functions applied only if not already present in pg_proc — see safety
# property 4 above. maintain_threat_event_partitions() is create-only-if-
# missing rather than unconditional CREATE OR REPLACE like the rest of
# SAFE_RPC_FUNCTIONS, so re-running this module never overwrites whatever
# version is already deployed.
CREATE_ONLY_IF_MISSING = frozenset({
    "maintain_threat_event_partitions",
})

_FUNCTION_NAME_PATTERN = re.compile(
    r"create\s+or\s+replace\s+function\s+(?:public\.)?(\w+)\s*\(", re.IGNORECASE
)


class MigrationError(Exception):
    pass


def _read_sql(filename: str) -> str:
    path = _SCHEMA_DIR / filename
    if not path.exists():
        raise MigrationError(f"{filename} not found at {path}")
    return path.read_text(encoding="utf-8")


def _defined_function_name(statement: str) -> str | None:
    """Returns the function name a CREATE OR REPLACE FUNCTION statement
    defines, or None for any other kind of statement (table DDL, RLS
    grants). Shared by both the SAFE_RPC_FUNCTIONS check and the
    CREATE_ONLY_IF_MISSING check below.
    """
    match = _FUNCTION_NAME_PATTERN.search(statement)
    return match.group(1) if match is not None else None


def _unsafe_function_name(statement: str) -> str | None:
    """Returns the function name if this statement defines a function not
    in SAFE_RPC_FUNCTIONS, else None.
    """
    name = _defined_function_name(statement)
    return name if name is not None and name not in SAFE_RPC_FUNCTIONS else None


def _function_exists(config: SchemaConfig, function_name: str) -> bool:
    """Live existence check against pg_proc, used only for functions in
    CREATE_ONLY_IF_MISSING. Fails safe: on any error, treats the function
    as existing so a check failure skips the statement rather than risking
    an unwanted overwrite.
    """
    try:
        result = execute_sql_with_retry(
            config,
            f"select exists (select 1 from pg_proc where proname = '{function_name}') as fn_exists;",
        )
    except SqlExecutionError as exc:
        logger.error("function existence check failed; assuming it exists", function=function_name, error=str(exc))
        return True

    rows = result if isinstance(result, list) else result.get("result", result.get("rows", []))
    if not rows:
        return True
    return bool(rows[0].get("fn_exists", True))


def apply_file(config: SchemaConfig, filename: str, dry_run: bool | None = None) -> dict:
    dry_run = config.migration.dry_run if dry_run is None else dry_run
    sql_text = _read_sql(filename)
    statements = split_statements(sql_text)

    log_migration_step(logger, f"apply_{filename}", "started", {"statement_count": len(statements), "dry_run": dry_run})

    applied = 0
    skipped = 0
    errors: list[dict] = []

    for i, statement in enumerate(statements):
        step_name = f"{filename}[{i}]"

        unsafe_name = _unsafe_function_name(statement)
        if unsafe_name is not None:
            log_migration_step(logger, step_name, "skipped_unsafe", {"function": unsafe_name})
            skipped += 1
            continue

        function_name = _defined_function_name(statement)
        if function_name in CREATE_ONLY_IF_MISSING and not dry_run and _function_exists(config, function_name):
            log_migration_step(logger, step_name, "skipped_existing", {"function": function_name})
            skipped += 1
            continue

        if dry_run:
            log_migration_step(logger, step_name, "dry_run", {"preview": statement[:200]})
            applied += 1
            continue

        try:
            execute_sql_with_retry(config, statement)
            log_migration_step(logger, step_name, "applied")
            applied += 1
        except SqlExecutionError as exc:
            log_migration_step(logger, step_name, "failed", {"error": str(exc), "status": exc.status})
            errors.append({"statement_index": i, "error": str(exc), "status": exc.status})

    result = {
        "file": filename,
        "dry_run": dry_run,
        "total_statements": len(statements),
        "applied": applied,
        "skipped_unsafe": skipped,
        "errors": errors,
    }
    log_migration_step(logger, f"apply_{filename}", "completed" if not errors else "completed_with_errors", result)
    return result


def apply_schema(config: SchemaConfig = DEFAULT_CONFIG, dry_run: bool | None = None) -> dict:
    """Applies tables.sql then rpcs.sql, in that order — RPCs reference
    tables (metric_rollups, anomalies) that must already exist.
    """
    tables_result = apply_file(config, config.migration.tables_file, dry_run)
    rpcs_result = apply_file(config, config.migration.rpcs_file, dry_run)

    return {
        "tables": tables_result,
        "rpcs": rpcs_result,
        "ok": not tables_result["errors"] and not rpcs_result["errors"],
    }


def main() -> int:
    result = apply_schema()
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
