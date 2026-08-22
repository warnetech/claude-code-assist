"""Context engineering: deciding what the model gets to see.

Retrieval quality dominates almost every other knob in a code-facing LLM
feature. A weaker model with the right three files beats a stronger model with
the wrong thirty, and it costs a tenth as much.

This module packs a repository into a token budget:

* :func:`walk_repo`     -- collect candidate files, respecting ignores.
* :func:`repo_map`      -- a cheap structural outline (signatures, not bodies).
* :func:`rank`          -- score files against a query with explainable signals.
* :func:`pack`          -- fill a budget, best-first, with elision that says so.

The estimator is chars/4 by default. When accuracy matters, pass a counter
backed by ``client.messages.count_tokens`` -- never ``tiktoken``, which models a
different tokenizer entirely.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_IGNORES = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", "target", ".next", ".nuxt", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", "vendor", "coverage", ".terraform", ".gradle", ".idea",
}

DEFAULT_EXTENSIONS = {
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rs", ".java",
    ".kt", ".rb", ".php", ".cs", ".swift", ".scala", ".c", ".h", ".cc", ".cpp",
    ".hpp", ".sql", ".sh", ".md", ".rst", ".toml", ".yaml", ".yml", ".json",
}

# Files that disproportionately explain a repo to a reader who has never seen it.
ANCHOR_NAMES = {
    "readme.md", "architecture.md", "claude.md", "agents.md", "contributing.md",
    "pyproject.toml", "package.json", "cargo.toml", "go.mod", "makefile",
}

TokenCounter = Callable[[str], int]


def estimate_tokens(text: str) -> int:
    """Rough token count: ~4 characters per token.

    Good enough for budgeting, wrong enough that you should not bill on it.
    """
    return max(1, len(text) // 4)


@dataclass(slots=True)
class Chunk:
    """A candidate piece of context with a provenance trail."""

    path: str
    text: str
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    tokens: int = 0
    kind: str = "file"

    def render(self) -> str:
        return f"<file path=\"{self.path}\">\n{self.text}\n</file>"


def walk_repo(
    root: str | Path,
    *,
    extensions: Iterable[str] | None = None,
    ignores: Iterable[str] | None = None,
    max_bytes: int = 400_000,
) -> list[Path]:
    """Collect candidate source files under ``root``.

    Skips ignored directories, unknown extensions, and files large enough to be
    generated (lockfiles, bundles, fixtures) -- those blow a budget without
    teaching the model anything.
    """
    root = Path(root)
    exts = set(extensions or DEFAULT_EXTENSIONS)
    skip = set(ignores or DEFAULT_IGNORES)
    found: list[Path] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if set(path.parts) & skip:
            continue
        if path.suffix.lower() not in exts:
            continue
        try:
            if path.stat().st_size > max_bytes:
                continue
        except OSError:  # pragma: no cover - races and permissions
            continue
        found.append(path)
    return found


# --------------------------------------------------------------------------- #
# Structural map
# --------------------------------------------------------------------------- #

_SIGNATURE_PATTERNS = (
    re.compile(r"^\s*(?:async\s+)?def\s+\w+\s*\(", re.M),
    re.compile(r"^\s*class\s+\w+", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+\w+", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+\w+", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:const|let)\s+\w+\s*[:=]\s*(?:async\s*)?\(", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:interface|type|enum)\s+\w+", re.M),
    re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?\w+\s*\(", re.M),
    re.compile(r"^\s*(?:pub\s+)?fn\s+\w+", re.M),
)


def outline(text: str, *, limit: int = 60) -> list[str]:
    """Extract declaration lines from source text.

    Regex, not a parser. That is a deliberate trade: it works on every language
    at once, degrades to "fewer lines" instead of "crash", and needs no
    per-language dependency. When you need real fidelity for one language, swap
    in that language's AST here.
    """
    hits: list[tuple[int, str]] = []
    for pattern in _SIGNATURE_PATTERNS:
        for match in pattern.finditer(text):
            end = text.find("\n", match.start())
            line = text[match.start() : end if end != -1 else len(text)]
            hits.append((match.start(), line.rstrip().rstrip("{:")))
    seen: set[str] = set()
    ordered: list[str] = []
    for _, line in sorted(hits):
        stripped = line.strip()
        if stripped and stripped not in seen:
            seen.add(stripped)
            ordered.append(stripped)
        if len(ordered) >= limit:
            break
    return ordered


def repo_map(paths: Sequence[Path], root: str | Path, *, per_file: int = 12) -> str:
    """A compact structural map: paths plus their top declarations.

    Put this in the *stable prefix* of a long-running session. It is small, it
    changes rarely, and it lets the model ask for the right file by name instead
    of guessing -- which is what actually collapses retrieval cost.
    """
    root = Path(root)
    lines: list[str] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:  # pragma: no cover
            continue
        rel = path.relative_to(root).as_posix()
        decls = outline(text, limit=per_file)
        lines.append(f"{rel}")
        lines.extend(f"  {d}" for d in decls)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def _terms(text: str) -> set[str]:
    """Tokenize into lowercase terms, splitting camelCase and snake_case."""
    out: set[str] = set()
    for word in _WORD.findall(text):
        out.add(word.lower())
        for part in re.split(r"_|(?<=[a-z0-9])(?=[A-Z])", word):
            if len(part) > 2:
                out.add(part.lower())
    return out


def rank(
    query: str,
    paths: Sequence[Path],
    root: str | Path,
    *,
    pinned: Iterable[str] = (),
    recent: Iterable[str] = (),
) -> list[Chunk]:
    """Score files against a query, with the reason for each score attached.

    Signals, in rough order of how much they matter in practice:

    * a path the caller pinned (always first -- the human knows something)
    * query terms appearing in the *path* (a strong, cheap signal)
    * query terms appearing in the *body*, saturating so one file cannot win by
      repeating a word two hundred times
    * recent edits (git status, open editors) -- proximity to the current task
    * anchor files that orient a reader who has never seen the repo

    The ``reasons`` list is the point. A retrieval step you cannot explain is a
    retrieval step you cannot debug when it starts returning the wrong files.
    """
    root = Path(root)
    wanted = _terms(query)
    pinned_set = {Path(p).as_posix() for p in pinned}
    recent_set = {Path(p).as_posix() for p in recent}
    chunks: list[Chunk] = []

    for path in paths:
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:  # pragma: no cover
            continue

        score = 0.0
        reasons: list[str] = []

        if rel in pinned_set:
            score += 1000.0
            reasons.append("pinned")

        path_hits = wanted & _terms(rel)
        if path_hits:
            score += 12.0 * len(path_hits)
            reasons.append(f"path matches {sorted(path_hits)}")

        body = _terms(text)
        body_hits = wanted & body
        if body_hits:
            # Saturating: the 10th distinct match matters much less than the 1st.
            score += 20.0 * (len(body_hits) / (len(body_hits) + 4))
            reasons.append(f"body matches {len(body_hits)} terms")

        if rel in recent_set:
            score += 25.0
            reasons.append("recently edited")

        if path.name.lower() in ANCHOR_NAMES:
            score += 8.0
            reasons.append("anchor file")

        # Mild preference for smaller files at equal relevance: three small
        # files usually explain more than one large one for the same budget.
        score -= min(5.0, len(text) / 20_000)

        chunks.append(
            Chunk(
                path=rel,
                text=text,
                score=score,
                reasons=reasons,
                tokens=estimate_tokens(text),
            )
        )

    chunks.sort(key=lambda c: (-c.score, c.path))
    return chunks


# --------------------------------------------------------------------------- #
# Packing
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class Packed:
    """The result of filling a budget."""

    text: str
    tokens: int
    included: list[str]
    elided: list[str]
    budget: int

    @property
    def utilization(self) -> float:
        return self.tokens / self.budget if self.budget else 0.0


def pack(
    chunks: Sequence[Chunk],
    *,
    budget_tokens: int = 60_000,
    counter: TokenCounter = estimate_tokens,
    head_lines: int = 120,
    tail_lines: int = 40,
    min_chunk_tokens: int = 200,
) -> Packed:
    """Fill a token budget best-first, truncating visibly rather than silently.

    Two rules earn their keep:

    * **Never silently truncate.** A file that got cut carries an explicit
      ``... N lines elided ...`` marker, so the model knows to ask for the rest
      instead of confidently reasoning about code it never saw.
    * **Skip, do not shrink to nothing.** Below ``min_chunk_tokens`` a fragment
      is noise; the budget is better spent finishing the next file.
    """
    parts: list[str] = []
    included: list[str] = []
    elided: list[str] = []
    used = 0

    for chunk in chunks:
        remaining = budget_tokens - used
        if remaining <= min_chunk_tokens:
            elided.append(chunk.path)
            continue

        body = chunk.text
        cost = counter(body)

        if cost > remaining:
            lines = body.splitlines()
            if len(lines) > head_lines + tail_lines:
                cut = len(lines) - head_lines - tail_lines
                body = "\n".join(
                    lines[:head_lines]
                    + [f"\n... {cut} lines elided from {chunk.path} ...\n"]
                    + lines[-tail_lines:]
                )
                cost = counter(body)
            if cost > remaining:
                elided.append(chunk.path)
                continue

        parts.append(Chunk(path=chunk.path, text=body).render())
        included.append(chunk.path)
        used += cost

    if elided:
        parts.append(
            "<elided-files note=\"not included; ask for any of these by path if needed\">\n"
            + "\n".join(elided)
            + "\n</elided-files>"
        )

    return Packed(
        text="\n\n".join(parts),
        tokens=used,
        included=included,
        elided=elided,
        budget=budget_tokens,
    )


def build_context(
    query: str,
    root: str | Path,
    *,
    budget_tokens: int = 60_000,
    pinned: Iterable[str] = (),
    recent: Iterable[str] = (),
    counter: TokenCounter = estimate_tokens,
) -> Packed:
    """walk -> rank -> pack, in one call. The 90% path."""
    paths = walk_repo(root)
    ranked = rank(query, paths, root, pinned=pinned, recent=recent)
    return pack(ranked, budget_tokens=budget_tokens, counter=counter)
