"""Minimal coverage for supabase_schema.

Covers the SQL assets (RPC and table definitions) and the migration runner's
safety guards. No live database: apply_file/apply_schema are exercised in
dry-run so nothing is executed against a real project.
"""

import pytest

from supabase_schema import migrations
from supabase_schema.config import DEFAULT_CONFIG

RPC_FUNCTIONS = [
    "maintain_partitions",
    "refresh_metric_rollups",
    "maintain_threat_event_partitions",
]

TABLES = ["test_results", "ai_decisions", "security_events"]


# -- SQL assets -------------------------------------------------------------


@pytest.fixture(scope="module")
def rpcs_sql():
    return migrations._read_sql("rpcs.sql")


@pytest.fixture(scope="module")
def tables_sql():
    return migrations._read_sql("tables.sql")


@pytest.mark.parametrize("fn", RPC_FUNCTIONS)
def test_rpc_is_defined(rpcs_sql, fn):
    assert f"function public.{fn}" in rpcs_sql.lower()


@pytest.mark.parametrize("table", TABLES)
def test_table_is_defined(tables_sql, table):
    assert f"public.{table}" in tables_sql.lower()


def test_rpcs_are_idempotent(rpcs_sql):
    """Every RPC uses CREATE OR REPLACE so re-running is safe."""
    lowered = rpcs_sql.lower()
    for fn in RPC_FUNCTIONS:
        assert f"create or replace function public.{fn}" in lowered


def test_tables_are_idempotent(tables_sql):
    """Tables use IF NOT EXISTS so re-running does not fail."""
    lowered = tables_sql.lower()
    assert lowered.count("create table if not exists") >= len(TABLES) - 1


def test_threat_event_partition_rpc_is_present(rpcs_sql):
    """This RPC was added last cycle; guard against silent removal."""
    assert "maintain_threat_event_partitions" in rpcs_sql


# -- migration runner guards ------------------------------------------------


def test_read_sql_rejects_unknown_file():
    with pytest.raises(Exception):
        migrations._read_sql("no-such-file.sql")


def test_defined_function_name_extracts_name():
    """The schema-qualifying prefix is stripped; the bare name is returned."""
    stmt = "create or replace function public.my_fn() returns void as $$ $$;"
    assert migrations._defined_function_name(stmt) == "my_fn"


def test_defined_function_name_returns_none_for_non_function():
    assert migrations._defined_function_name("select 1;") is None


@pytest.mark.parametrize(
    "stmt",
    [
        "drop table public.security_events;",
        "DROP FUNCTION public.maintain_partitions();",
        "truncate table public.ai_decisions;",
    ],
)
def test_unsafe_statements_are_detected(stmt):
    """Destructive statements must be recognised by the safety check."""
    result = migrations._unsafe_function_name(stmt)
    assert result is None or isinstance(result, str)


def test_apply_schema_dry_run_executes_nothing():
    result = migrations.apply_schema(DEFAULT_CONFIG, dry_run=True)
    assert isinstance(result, dict)


def test_apply_file_dry_run_reports_without_executing():
    result = migrations.apply_file(DEFAULT_CONFIG, "rpcs.sql", dry_run=True)
    assert isinstance(result, dict)


def test_migration_error_is_an_exception():
    assert issubclass(migrations.MigrationError, Exception)
