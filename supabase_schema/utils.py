"""Helper functions: SQL execution against the Supabase Management API,
error handling, and retry logic.

Standard library only (urllib), matching every other package in this
system. `execute_sql` is the one function that actually talks to Supabase;
everything else in migrations.py is built on top of it.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Optional

from .config import SchemaConfig


class SqlExecutionError(Exception):
    def __init__(self, message: str, status: Optional[int] = None, detail: object = None) -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail


def split_statements(sql_text: str) -> list[str]:
    """Splits a .sql file into individual statements on top-level semicolons.
    Tracks two constructs that would otherwise cause a false split: `--`
    line comments (a semicolon in prose must not end a statement — this
    file's own header comments have one) and `$tag$...$tag$` dollar-quoted
    function bodies. Naive beyond that: none of this package's SQL uses
    semicolons inside string literals, which would need a third state.
    """
    statements: list[str] = []
    buffer: list[str] = []
    in_dollar_quote = False
    dollar_tag = ""
    in_line_comment = False
    i = 0
    while i < len(sql_text):
        if sql_text[i] == "\n":
            in_line_comment = False
            buffer.append(sql_text[i])
            i += 1
            continue

        if in_line_comment:
            buffer.append(sql_text[i])
            i += 1
            continue

        if not in_dollar_quote and sql_text.startswith("--", i):
            in_line_comment = True
            buffer.append(sql_text[i])
            i += 1
            continue

        if sql_text[i] == "$" and not in_dollar_quote:
            end = sql_text.find("$", i + 1)
            if end != -1:
                dollar_tag = sql_text[i:end + 1]
                in_dollar_quote = True
                buffer.append(dollar_tag)
                i = end + 1
                continue
        elif in_dollar_quote and sql_text.startswith(dollar_tag, i):
            buffer.append(dollar_tag)
            i += len(dollar_tag)
            in_dollar_quote = False
            continue

        if sql_text[i] == ";" and not in_dollar_quote:
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
            i += 1
            continue

        buffer.append(sql_text[i])
        i += 1

    tail = "".join(buffer).strip()
    if tail:
        statements.append(tail)
    return statements


def execute_sql(config: SchemaConfig, sql: str) -> dict:
    """Runs one SQL statement via the Supabase Management API's database
    query endpoint. Requires `config.supabase.project_ref` and
    `management_api_token` — the project's anon/service-role keys cannot
    execute DDL, only PostgREST row operations.
    """
    if not config.supabase.project_ref or not config.supabase.management_api_token:
        raise SqlExecutionError("management_api_token and project_ref are required to execute SQL")

    url = f"https://api.supabase.com/v1/projects/{config.supabase.project_ref}/database/query"
    body = json.dumps({"query": sql}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {config.supabase.management_api_token}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=config.migration.request_timeout_seconds) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read())
        except (json.JSONDecodeError, UnicodeDecodeError):
            detail = None
        raise SqlExecutionError(f"Supabase Management API returned {exc.code}", status=exc.code, detail=detail) from exc
    except urllib.error.URLError as exc:
        raise SqlExecutionError(f"Supabase Management API unreachable: {exc.reason}") from exc


def execute_sql_with_retry(config: SchemaConfig, sql: str, sleep_fn=time.sleep) -> dict:
    """Retries only on 5xx/429 — a malformed statement (4xx) will not
    start working by waiting, so it fails immediately with the real error.
    """
    attempt = 0
    delay = config.migration.base_retry_delay_seconds
    last_error: Optional[SqlExecutionError] = None

    while attempt <= config.migration.max_retries:
        try:
            return execute_sql(config, sql)
        except SqlExecutionError as exc:
            last_error = exc
            if exc.status is not None and exc.status not in (429, 500, 502, 503, 504):
                raise
            attempt += 1
            if attempt > config.migration.max_retries:
                break
            sleep_fn(delay)
            delay *= 2

    raise last_error  # type: ignore[misc]
