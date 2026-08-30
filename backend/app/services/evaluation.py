"""Reading the evaluation runs off disk.

The harness writes, per configuration, a `summary.csv` and one `qNN.txt` per
question. Those files are what Chapter 4 cites, so they are the authority.
Nothing here copies them into a table — a database copy would be a second
source of truth able to disagree with the evidence, which is the failure this
project has spent two phases chasing elsewhere.

**The runs are not uniform, and that shaped this module.** `--json` was added
to the harness partway through data collection, so C0, C4 and C5 have a full
JSON log appended to each answer — sources, per-stage latencies, agent
iterations, verification — while C1, C1-CONTROL, C2 and C3 have only the answer
text. `summary.csv` is the one thing every run has, and it carries the question
and the timings, so it is read first and the log is treated as extra detail
where it exists.

The alternative was to expose only the three configurations with logs, which
would have quietly dropped C3 — the portal default and the headline of the
ablation — from the comparison. Better to serve every run and say which parts
of each were recorded.

One module rather than one reader per route: `/admin/evaluations` and the
public comparison parse the same files, and two parsers over one format drift.
"""

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

# Mounted read-only at /app/eval by docker-compose. Before that mount existed
# this pointed at a path absent from the image, and the endpoints reported "no
# results directory" — which reads as an empty evaluation rather than a missing
# volume.
EVAL_ROOT = Path(os.environ.get("EVAL_RESULTS_DIR", "/app/eval/results"))

_QUESTION_FILE = re.compile(r"^q\d+$")

# The harness writes each answer as:
#
#     <answer text>
#
#     Sources:
#       [S1] <citation label>
#             <url>
#
#       N retrieved chunk(s) omitted for context budget.
#
#     [C3 | model | retrieval 12683ms, generation 15737ms]
#
# followed, in the runs made after `--json` was added, by a JSON log.
#
# The sources are parsed from this block rather than from the log's `sources`
# field, which holds bare chunk ids. The block has the citation label and the
# URL — what a reader needs — and unlike the log it exists in every run.
_SOURCES_HEADING = "\nSources:"
_SOURCE_LINE = re.compile(r"^\s*\[S(\d+)\]\s*(.+?)\s*$")
_URL_LINE = re.compile(r"^\s+(https?://\S+)\s*$")
_OMITTED_LINE = re.compile(r"^\s*(\d+)\s+retrieved chunk")
_TRAILER_LINE = re.compile(r"^\[[^|\]]+\|[^\]]*\]\s*$")

# Preferred source for the canonical question list. Every run answers the same
# twenty; C3 is the portal default, so it is the natural reference.
_REFERENCE_ORDER = ("C3", "C0", "C5")


@dataclass(frozen=True)
class RunAnswer:
    """One configuration's recorded answer to one question."""

    config: str
    question_id: str
    question: str
    answer: str
    sources: list[dict[str, str | None]]
    sources_recorded: bool
    omitted_chunks: int | None
    used_demo_sources: bool
    latency_ms: float | None
    retrieval_ms: float | None
    generation_ms: float | None
    iteration_count: int | None
    stop_reason: str | None
    verification: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config,
            "question_id": self.question_id,
            "question": self.question,
            "answer": self.answer,
            "sources": self.sources,
            # Distinguishes "cited nothing" from "this run recorded no source
            # block". Without it an empty list would read as the former.
            "sources_recorded": self.sources_recorded,
            # How many retrieved passages were dropped to fit the context
            # budget — the clearest single number for what retrieval found
            # versus what generation was actually shown.
            "omitted_chunks": self.omitted_chunks,
            "used_demo_sources": self.used_demo_sources,
            "latency_ms": self.latency_ms,
            "retrieval_ms": self.retrieval_ms,
            "generation_ms": self.generation_ms,
            "iteration_count": self.iteration_count,
            "stop_reason": self.stop_reason,
            "verification": self.verification,
        }


def available_configs() -> list[str]:
    """Configuration directories that actually hold answers, in run order."""
    if not EVAL_ROOT.exists():
        return []
    configs = [
        directory.name
        for directory in EVAL_ROOT.iterdir()
        if directory.is_dir() and any(directory.glob("q*.txt"))
    ]
    return sorted(configs, key=_config_sort_key)


def _config_sort_key(name: str) -> tuple[int, str]:
    """C0 … C5 in order, with C1-CONTROL beside C1 rather than at the end."""
    match = re.match(r"^C(\d+)", name)
    return (int(match.group(1)) if match else 99, name)


@lru_cache(maxsize=16)
def _summary(config: str) -> dict[str, dict[str, str]]:
    """`summary.csv` keyed by question id. Cached; a finished run never changes."""
    path = EVAL_ROOT / config / "summary.csv"
    if not path.is_file():
        return {}
    rows: dict[str, dict[str, str]] = {}
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            for row in csv.DictReader(handle):
                question_id = (row.get("id") or "").strip()
                if question_id:
                    rows[question_id] = row
    except OSError:
        return {}
    return rows


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _split_answer(body: str) -> tuple[str, list[dict[str, str | None]], int | None]:
    """Separate the answer from the source block and the trailing metadata line.

    Without this the answer rendered on the comparison page carried the
    harness's own formatting with it — a `Sources:` list and a
    `[C3 | model | retrieval …ms]` line — which is output for a terminal, not
    an answer the system gave.
    """
    heading = body.find(_SOURCES_HEADING)
    if heading == -1:
        # No source block: strip only the trailing metadata line.
        lines = [line for line in body.splitlines() if not _TRAILER_LINE.match(line.strip())]
        return "\n".join(lines).strip(), [], None

    answer = body[:heading].strip()
    sources: list[dict[str, str | None]] = []
    omitted: int | None = None

    for line in body[heading + len(_SOURCES_HEADING) :].splitlines():
        source_match = _SOURCE_LINE.match(line)
        if source_match:
            sources.append(
                {
                    "marker": f"[S{source_match.group(1)}]",
                    "label": source_match.group(2),
                    "url": None,
                }
            )
            continue

        url_match = _URL_LINE.match(line)
        if url_match and sources:
            # The URL belongs to the label immediately above it.
            sources[-1]["url"] = url_match.group(1)
            continue

        omitted_match = _OMITTED_LINE.match(line)
        if omitted_match:
            omitted = int(omitted_match.group(1))

    return answer, sources, omitted


def load_answer(config: str, question_id: str) -> RunAnswer | None:
    if not _QUESTION_FILE.match(question_id):
        return None

    path = EVAL_ROOT / config / f"{question_id}.txt"
    if not path.is_file():
        return None

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # The log, where the run recorded one. Located by the first line beginning
    # an object at column zero, because the answer above can contain braces.
    log: dict[str, Any] = {}
    start = text.find("\n{")
    if start != -1:
        try:
            log = json.loads(text[start:])
        except json.JSONDecodeError:
            start = -1

    body = text[:start] if start != -1 else text
    answer, sources, omitted = _split_answer(body)

    row = _summary(config).get(question_id, {})
    retrieval = log.get("retrieval") or {}

    wall = _number(row.get("wall_seconds"))
    return RunAnswer(
        config=config,
        question_id=question_id,
        question=str(row.get("question") or log.get("question") or ""),
        answer=answer,
        sources=sources,
        sources_recorded=_SOURCES_HEADING in body,
        omitted_chunks=omitted,
        used_demo_sources=bool(log.get("used_demo_sources")),
        latency_ms=_number(log.get("latency_ms")) or (wall * 1000 if wall else None),
        retrieval_ms=_number(log.get("retrieval_ms")) or _number(row.get("retrieval_ms")),
        generation_ms=_number(log.get("generation_ms")) or _number(row.get("generation_ms")),
        iteration_count=retrieval.get("iteration_count"),
        stop_reason=retrieval.get("stop_reason"),
        verification=log.get("verification") or None,
    )


@lru_cache(maxsize=1)
def questions() -> list[dict[str, str]]:
    """Every evaluated question, from `summary.csv` — the one file every run has."""
    configs = available_configs()
    if not configs:
        return []

    reference = next((name for name in _REFERENCE_ORDER if name in configs), configs[0])
    rows = _summary(reference)
    return [
        {
            "id": question_id,
            "question": (row.get("question") or "").strip(),
            "category": (row.get("category") or "").strip(),
        }
        for question_id, row in sorted(rows.items())
        if (row.get("question") or "").strip()
    ]


__all__ = [
    "EVAL_ROOT",
    "RunAnswer",
    "available_configs",
    "load_answer",
    "questions",
]
