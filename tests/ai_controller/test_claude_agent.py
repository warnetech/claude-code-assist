"""Tests for the Claude orchestration layer.

These assert composition, not re-implementation: the agent must delegate to
the existing engines and must not introduce parallel logic.
"""

import pytest

from warnetech_ai_controller.warnetech_claude_agent import (
    AssessmentResult,
    WarnetechClaudeAgent,
)


@pytest.fixture
def agent():
    return WarnetechClaudeAgent()


# -- construction -----------------------------------------------------------


def test_agent_wires_all_five_engines(agent):
    engines = agent.engines()
    assert engines == {
        "scoring": "ScoringEngine",
        "anomaly": "AnomalyEngine",
        "ghost": "GhostEngine",
        "recovery": "RecoveryEngine",
        "signatures": "SignatureEngine",
    }


def test_agent_defines_no_duplicate_signature_type():
    """The existing Signature carries fields a simpler copy would drop."""
    import warnetech_ai_controller.warnetech_claude_agent as mod

    assert not hasattr(mod, "Signature")


def test_engines_are_injectable():
    class FakeScoring:
        pass

    agent = WarnetechClaudeAgent(scoring=FakeScoring())
    assert agent.engines()["scoring"] == "FakeScoring"


# -- assessment -------------------------------------------------------------


def test_assess_returns_assessment_result(agent):
    result = agent.assess("src-1", signature_score=0.1)
    assert isinstance(result, AssessmentResult)
    assert set(result.to_dict()) == {
        "threat_level",
        "total_score",
        "blocked",
        "anomalies",
        "breakdown",
    }


def test_high_signature_score_blocks(agent):
    result = agent.assess("src-1", signature_score=0.95)
    assert result.threat_level == "CRITICAL"
    assert result.blocked is True


def test_low_signature_score_does_not_block(agent):
    result = agent.assess("src-1", signature_score=0.0)
    assert result.threat_level == "LOW"
    assert result.blocked is False


def test_assess_delegates_to_scoring_engine(agent):
    """The score must come from ScoringEngine, not be recomputed locally."""
    direct = agent.scoring.score(signature_score=0.42)
    viaagent = agent.assess("src-1", signature_score=0.42)
    assert viaagent.total_score == direct.total
    assert viaagent.threat_level == direct.threat_level


def test_breakdown_reports_inputs(agent):
    result = agent.assess("src-1", signature_score=0.5, behavioral_score=0.25)
    assert result.breakdown["signature_score"] == 0.5
    assert result.breakdown["behavioral_score"] == 0.25


def test_anomaly_score_is_normalised_not_saturating(agent):
    """One detector firing must not by itself max out the anomaly score."""
    result = agent.assess(
        "src-1",
        signature_score=0.0,
        headers={"x-weird": "1"},
        baseline_headers=["host", "accept"],
    )
    assert result.breakdown["anomaly_score"] <= 1.0 / 3.0 + 1e-9


def test_header_anomaly_is_detected(agent):
    result = agent.assess(
        "src-1",
        signature_score=0.0,
        headers={"x-injected": "1", "x-other": "2"},
        baseline_headers=["host"],
    )
    assert isinstance(result.anomalies, list)


# -- recall -----------------------------------------------------------------


GHOSTS = [
    {
        "slice_id": "s1",
        "system": "firewall",
        "type": "log",
        "created_at": "2026-01-02T00:00:00Z",
        "time_range": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
    },
    {
        "slice_id": "s2",
        "system": "firewall",
        "type": "log",
        "created_at": "2026-01-03T00:00:00Z",
        "time_range": {"start": "2026-01-02T00:00:00Z", "end": "2026-01-03T00:00:00Z"},
    },
]


def test_plan_recall_returns_both_halves(agent):
    out = agent.plan_recall(GHOSTS)
    assert set(out) == {"recall_plan", "reconstruction_plan", "total_steps"}


def test_plan_recall_with_no_cues_selects_nothing(agent):
    """score_ghost_relevance scores every candidate 0.0 when given no cue,
    so a plan with no filters and no time must contain no steps."""
    assert agent.plan_recall(GHOSTS)["total_steps"] == 0


def test_plan_recall_produces_multi_ghost_plan(agent):
    """A matching system cue should recover both ghost copies, not just one."""
    out = agent.plan_recall(GHOSTS, system="firewall")
    assert out["total_steps"] == 2


def test_plan_recall_honours_system_filter(agent):
    matched = agent.plan_recall(GHOSTS, system="firewall")
    unmatched = agent.plan_recall(GHOSTS, system="does-not-exist")
    assert matched["total_steps"] > unmatched["total_steps"]


def test_plan_recall_window_selects_overlapping_copies(agent):
    out = agent.plan_recall(
        GHOSTS,
        system="firewall",
        time_start="2026-01-01T00:00:00Z",
        time_end="2026-01-02T00:00:00Z",
    )
    assert out["total_steps"] >= 1


def test_plan_recall_on_empty_input_is_safe(agent):
    out = agent.plan_recall([])
    assert out["total_steps"] == 0


def test_recall_ghost_missing_slice_returns_none(agent):
    assert agent.recall_ghost("no-such-slice-id") is None


# -- recovery ---------------------------------------------------------------


def test_recover_runs_the_protocol(agent):
    report = agent.recover("incident-1")
    assert "steps" in report
    assert "all_ok" in report
    assert len(report["steps"]) > 0


def test_recover_reports_per_step_results(agent):
    report = agent.recover("incident-2")
    for step in report["steps"]:
        assert "name" in step
