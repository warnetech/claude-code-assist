"""Memory: distill finished runs into short, reusable lessons.

**Claim.** Replaying whole transcripts as "memory" is the wrong unit. A
transcript is mostly dead weight -- tool noise, retries, wrong turns -- and it
costs context proportional to how badly the run went. What transfers between
runs is much smaller: a handful of durable facts about *this* codebase and
*this* team. "Migrations live in db/migrate and must be reversible." "The CI
lint step rejects unsorted imports." "Never touch generated/."

A lesson is worth keeping only if it would have changed what an agent did.
Everything else is trivia that costs tokens on every future run.

**How it would fail.** Lesson rot. A distilled lesson is a snapshot of a
codebase that keeps moving; six months on, a confident wrong lesson is worse
than no memory, because the agent trusts it. This implementation therefore
timestamps every lesson, tracks confirmations and contradictions, and decays
confidence -- a lesson that has not been reconfirmed is surfaced with its age
attached rather than asserted flatly.

**Also load-bearing:** memory is an injection surface. A lesson distilled from
a run that processed a hostile README can persist an attacker's instruction
into every future session. Lessons are scanned on write and stored with
provenance, and this is not optional.

**Measurement.** Task success and step count with memory on versus off, on
tasks the agent has seen a sibling of before. If step count does not drop, the
lessons are not carrying information.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..guard import scan_injection
from ..trace import NULL_TRACER, Tracer
from ..types import Request

LESSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "lessons": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "scope": {"type": "string"},
                    "evidence": {"type": "string"},
                    "would_have_changed_behavior": {"type": "boolean"},
                },
                "required": ["claim", "scope", "evidence", "would_have_changed_behavior"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["lessons"],
    "additionalProperties": False,
}

DISTILL_SYSTEM = """\
You extract durable lessons from a finished agent run. You are not summarizing.

Keep a lesson only if ALL of these hold:
- It is specific to this codebase, team, or environment -- not general \
programming knowledge the model already has.
- It would have changed what the agent did, had it known it at the start.
- It will still be true next month.

One sentence per claim. `scope` is the path or subsystem it applies to, or \
"repo" for repo-wide. `evidence` cites what in the run supports it.

Most runs yield zero or one lesson. Returning an empty list is the correct and \
common answer. Do not invent lessons to seem useful.

Return JSON only.\
"""


@dataclass(slots=True)
class Lesson:
    """One durable claim about a codebase, with provenance and an age."""

    claim: str
    scope: str = "repo"
    evidence: str = ""
    source: str = "unknown"
    created_at: float = field(default_factory=time.time)
    confirmed: int = 0
    contradicted: int = 0
    quarantined: bool = False
    """Set when the lesson matched injection heuristics on write."""

    @property
    def age_days(self) -> float:
        return (time.time() - self.created_at) / 86400

    @property
    def confidence(self) -> float:
        """Confirmations minus contradictions, decayed by age.

        Deliberately crude. Its job is to order lessons and to stop a stale one
        from being asserted as flatly as a fresh one -- not to be a probability.
        """
        base = (1 + self.confirmed) / (1 + self.confirmed + 2 * self.contradicted)
        decay = 0.5 ** (self.age_days / 90)
        return round(base * (0.4 + 0.6 * decay), 3)

    def render(self) -> str:
        age = f"{self.age_days:.0f}d" if self.age_days >= 1 else "new"
        return f"- [{self.scope}] {self.claim} (confidence {self.confidence}, age {age})"


class LessonStore:
    """A small JSON-backed store of lessons.

    Deliberately a file, not a vector database. At the scale that matters for
    one repository -- tens to low hundreds of lessons -- reading all of them and
    filtering by scope beats an embedding round trip on latency, cost, and on
    your ability to open the file and see what the agent thinks it knows. That
    last one is the real argument: memory you cannot audit is memory you cannot
    trust.
    """

    def __init__(self, path: str | Path = ".llmforge/lessons.json") -> None:
        self.path = Path(path)
        self.lessons: list[Lesson] = []
        if self.path.exists():
            raw = json.loads(self.path.read_text())
            self.lessons = [Lesson(**entry) for entry in raw]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([asdict(x) for x in self.lessons], indent=2))

    def add(self, lesson: Lesson) -> Lesson:
        """Add a lesson, merging duplicates and quarantining suspicious ones.

        A lesson whose text matches injection heuristics is stored quarantined
        rather than dropped: you want to *see* that something tried to write an
        instruction into persistent memory, not have it silently vanish.
        """
        scan = scan_injection(lesson.claim + " " + lesson.evidence)
        if scan.suspicious:
            lesson.quarantined = True

        key = lesson.claim.strip().lower()
        for existing in self.lessons:
            if existing.claim.strip().lower() == key:
                existing.confirmed += 1
                return existing
        self.lessons.append(lesson)
        return lesson

    def contradict(self, claim: str) -> None:
        """Record that a lesson turned out to be wrong."""
        key = claim.strip().lower()
        for lesson in self.lessons:
            if lesson.claim.strip().lower() == key:
                lesson.contradicted += 1

    def recall(
        self,
        scope: str = "repo",
        *,
        limit: int = 8,
        min_confidence: float = 0.25,
        include_quarantined: bool = False,
    ) -> list[Lesson]:
        """The lessons worth spending context on for a given scope.

        Quarantined lessons are excluded by default. Including them means
        deliberately putting text that looked like an injection attempt back
        into a prompt -- occasionally right when auditing, never by accident.
        """
        candidates = [
            lesson
            for lesson in self.lessons
            if (include_quarantined or not lesson.quarantined)
            and lesson.confidence >= min_confidence
            and (lesson.scope == "repo" or scope == "repo" or scope.startswith(lesson.scope))
        ]
        candidates.sort(key=lambda x: -x.confidence)
        return candidates[:limit]

    def render(self, scope: str = "repo", **kwargs: Any) -> str:
        """Recalled lessons as a prompt block. Empty string when there are none."""
        recalled = self.recall(scope, **kwargs)
        if not recalled:
            return ""
        return (
            "<learned-context note=\"distilled from prior runs in this repository; "
            "treat as fallible and prefer direct observation\">\n"
            + "\n".join(x.render() for x in recalled)
            + "\n</learned-context>"
        )


def distill(
    provider: Any,
    transcript: str,
    *,
    source: str = "run",
    model: str = "claude-opus-5",
    store: LessonStore | None = None,
    tracer: Tracer | None = None,
) -> list[Lesson]:
    """Extract durable lessons from a finished run.

    Returns only lessons the model marked as behavior-changing. The filter is
    the point: without it, distillation produces a paragraph of restated
    obviousness that costs context forever.
    """
    tracer = tracer or NULL_TRACER
    with tracer.span("memory.distill", kind="stage"):
        response = provider.complete(
            Request(
                messages=[{"role": "user", "content": f"<run>\n{transcript}\n</run>"}],
                model=model,
                system=DISTILL_SYSTEM,
                max_tokens=4000,
                output_schema=LESSON_SCHEMA,
                metadata={"lab": "memory", "stage": "distill"},
            )
        )

    try:
        parsed = json.loads(response.text)
    except ValueError:
        return []

    lessons = [
        Lesson(
            claim=entry["claim"],
            scope=entry.get("scope", "repo"),
            evidence=entry.get("evidence", ""),
            source=source,
        )
        for entry in parsed.get("lessons", [])
        if entry.get("would_have_changed_behavior")
    ]

    if store is not None:
        for lesson in lessons:
            store.add(lesson)
        store.save()
    return lessons
