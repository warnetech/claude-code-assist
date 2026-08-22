"""Minimal coverage for warnetech_connectors.

Connectors fail soft by contract: on error they return {"error": ...} rather
than raising, so a command reports a clean failure instead of a traceback.
These tests pin that contract and the normalisation shapes.
"""

import pytest

from warnetech_connectors.intel_feeds import (
    fetch_intel_feed,
    normalize_intel,
    push_intel_to_control_plane,
)
from warnetech_connectors.reputation_services import (
    normalize_reputation,
    push_reputation_to_control_plane,
    query_reputation,
)


# -- intel feeds ------------------------------------------------------------


def test_fetch_unknown_source_fails_soft():
    """Unconfigured sources report status "disabled" rather than raising."""
    result = fetch_intel_feed("no-such-source")
    assert result["status"] == "disabled"
    assert result["records"] == []


def test_normalize_intel_returns_dict():
    assert isinstance(normalize_intel({}), dict)


def test_normalize_intel_tolerates_junk():
    for junk in ({}, {"unexpected": "shape"}, {"data": None}):
        assert isinstance(normalize_intel(junk), dict)


def test_push_intel_uses_injected_sink():
    captured = []

    def sink(records):
        captured.append(records)
        return len(records)

    result = push_intel_to_control_plane([{"indicator": "1.2.3.4"}], sink=sink)
    assert len(captured) == 1
    # records are normalised before they reach the sink
    pushed = captured[0][0]
    assert pushed["indicator"] == "1.2.3.4"
    assert "normalized_at" in pushed
    assert isinstance(result, dict)


def test_push_intel_with_empty_list():
    result = push_intel_to_control_plane([], sink=lambda r: 0)
    assert isinstance(result, dict)


# -- reputation services ----------------------------------------------------


def test_query_reputation_unknown_source_fails_soft():
    result = query_reputation("1.2.3.4", source="no-such-service")
    assert result["status"] == "disabled"
    assert result["target"] == "1.2.3.4"


def test_normalize_reputation_returns_dict():
    assert isinstance(normalize_reputation({}), dict)


def test_normalize_reputation_tolerates_string_verdict():
    """Regression: verdict arriving as a str crashed indicator_type, which
    lacked the isinstance guard its two neighbouring fields both had."""
    out = normalize_reputation({"target": "1.2.3.4", "verdict": "malicious"})
    assert out["indicator"] == "1.2.3.4"
    assert out["indicator_type"] == "url"
    assert out["confidence"] == 0.5
    assert out["severity"] == "medium"


def test_push_reputation_uses_injected_sink():
    captured = []
    push_reputation_to_control_plane(
        [{"target": "1.2.3.4", "verdict": "malicious"}],
        sink=lambda r: captured.append(r) or len(r),
    )
    assert len(captured) == 1


# -- module surface ---------------------------------------------------------


@pytest.mark.parametrize(
    "module",
    [
        "warnetech_connectors.intel_feeds",
        "warnetech_connectors.reputation_services",
        "warnetech_connectors.vuln_databases",
        "warnetech_connectors.siem_soar",
        "warnetech_connectors.log_aggregators",
        "warnetech_connectors.database",
        "warnetech_connectors.config",
    ],
)
def test_connector_modules_import(module):
    __import__(module)
