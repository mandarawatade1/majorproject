#!/usr/bin/env python3
"""
Runs the fixed eval question set through `python -m rag ask` inside the
running `api` container, for a given pipeline config (C0 by default), and
logs raw output + parsed timings so results are comparable across C0-C5.

Usage:
    python run_baseline_eval.py --config C0
    python run_baseline_eval.py --config C0 --questions eval_questions.json

Output:
    eval/results/<CONFIG>/<question_id>.txt   -- raw CLI output per question
    eval/results/<CONFIG>/summary.csv         -- one row per question with timings

Assumptions (check these against your actual CLI and adjust if wrong):
  - `docker compose exec -T api python -m rag ask "<question>" --config <C>`
    answers a question under config <C>. The index must have been built with
    the SAME config: `rag ask` selects the pipeline stages, not the chunks
    already in Chroma. Re-index with --reset when switching chunker
    (C0 <-> C1 and later).
  - The CLI prints a summary line like:
    [C0 | qwen2.5:7b-instruct-q4_K_M | retrieval 7025ms, generation 65571ms]
    This script parses that line for timings. If the format changes, update
    TIMING_RE.
"""

import argparse
import collections
import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path

# [\w-] not \w: config names may contain a hyphen (C1-CONTROL). With \w+ the
# whole pattern fails to match rather than matching a prefix, so every timing
# for such a config would come back blank -- silently, since parse_timings
# returns empty strings when it does not match.
TIMING_RE = re.compile(
    r"\[(?P<config>[\w-]+)\s*\|\s*(?P<model>[^|]+?)\s*\|\s*"
    r"retrieval\s+(?P<retrieval_ms>\d+)ms,\s*generation\s+(?P<generation_ms>\d+)ms\]"
)


def run_question(question: str, config: str) -> tuple[str, float]:
    """Runs one question through the CLI, returns (raw_stdout, wall_seconds).

    --config was previously missing here entirely, so every run silently
    used the CLI ask command default (C0), regardless of which folder the
    result was saved under. Fixed by threading the actual config through.
    """
    # --json is not optional for C4 and later. Without it the CLI prints only
    # the formatted answer, so stop_reason, iteration_count, rewritten_queries
    # and the per-arm chunk ids -- the whole evidential basis for the agentic
    # layer -- are never saved. It is harmless for C0-C3: the JSON is appended
    # after the answer, parse_timings still reads the summary line, and the
    # extra rows are exactly what a later audit needs (see architecture-plan
    # section 22.4, where an audit could not be settled for want of chunk ids).
    cmd = [
        "docker", "compose", "exec", "-T", "api",
        "python", "-m", "rag", "ask", question, "--config", config, "--json",
    ]
    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    wall = time.time() - start
    if result.returncode != 0:
        return f"ERROR (exit {result.returncode}):\n{result.stderr}", wall
    return result.stdout, wall


def parse_timings(raw_output: str) -> dict:
    m = TIMING_RE.search(raw_output)
    if not m:
        return {"config": "", "model": "", "retrieval_ms": "", "generation_ms": ""}
    d = m.groupdict()
    d["model"] = d["model"].strip()
    return d


def _final_sources(path) -> list | None:
    """The citation labels actually shown with the answer, or None if absent.

    Labels rather than chunk ids, so the comparison also works against results
    collected before --json was passed to the CLI.
    """
    if not Path(path).exists():
        return None
    out, grab = [], False
    for line in Path(path).read_text(errors="replace").splitlines():
        if line.startswith("Sources:"):
            grab = True
            continue
        if grab and line.strip().startswith("[S"):
            out.append(line.strip().split("] ", 1)[-1])
    return out


def parse_retrieval(raw_output: str) -> dict:
    """Pull the agentic fields out of the --json block, if there is one.

    The CLI prints the formatted answer and then the log as JSON, so the block
    starts at the first '{' on its own line. Empty values for C0-C3, which have
    no agent: `stop_reason` and `iterations` are populated only by C4 and later,
    which is what makes a C4 row distinguishable from a C3 row.
    """
    start = raw_output.find("\n{")
    if start == -1:
        return {"stop_reason": "", "iteration_count": "", "follow_up_queries": "",
                "sources_returned": ""}
    try:
        log = json.loads(raw_output[start:])
    except json.JSONDecodeError:
        return {"stop_reason": "PARSE_ERROR", "iteration_count": "",
                "follow_up_queries": "", "sources_returned": ""}

    retrieval = log.get("retrieval") or {}
    return {
        "stop_reason": retrieval.get("stop_reason") or "",
        "iteration_count": retrieval.get("iteration_count", ""),
        "follow_up_queries": " | ".join(retrieval.get("rewritten_queries") or []),
        "sources_returned": len(log.get("sources") or []),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="C0", help="Pipeline config to run; passed to `rag ask --config` and used as the output dir name")
    ap.add_argument("--questions", default="eval_questions.json")
    ap.add_argument("--outdir", default="eval/results")
    ap.add_argument("--compare", default="",
                    help="Another config's results dir to diff final sources against "
                         "(e.g. --compare C3), answering whether this config's extra "
                         "retrieval actually reached the answer")
    args = ap.parse_args()

    questions_path = Path(args.questions)
    if not questions_path.exists():
        print(f"ERROR: {questions_path} not found. Place eval_questions.json next to this script "
              f"or pass --questions <path>.", file=sys.stderr)
        sys.exit(1)

    data = json.loads(questions_path.read_text())
    questions = data["questions"]

    outdir = Path(args.outdir) / args.config
    outdir.mkdir(parents=True, exist_ok=True)
    summary_path = outdir / "summary.csv"

    print(f"Running {len(questions)} questions against config={args.config}")
    print(f"Output: {outdir}/")

    rows = []
    for i, q in enumerate(questions, 1):
        qid, category, question = q["id"], q["category"], q["question"]
        print(f"[{i}/{len(questions)}] {qid} ({category}): {question[:60]}...")

        raw, wall = run_question(question, args.config)
        (outdir / f"{qid}.txt").write_text(raw)

        timings = parse_timings(raw)
        agent = parse_retrieval(raw)
        rows.append({
            "id": qid,
            "category": category,
            "question": question,
            "wall_seconds": round(wall, 1),
            "retrieval_ms": timings["retrieval_ms"],
            "generation_ms": timings["generation_ms"],
            "model": timings["model"],
            "stop_reason": agent["stop_reason"],
            "iteration_count": agent["iteration_count"],
            "follow_up_queries": agent["follow_up_queries"],
            "sources_returned": agent["sources_returned"],
            "output_file": f"{qid}.txt",
        })

        print(f"    done in {wall:.1f}s (retrieval={timings['retrieval_ms']}ms, "
              f"generation={timings['generation_ms']}ms)")

    with open(summary_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    total_wall = sum(r["wall_seconds"] for r in rows)
    print(f"\nDone. {len(rows)} questions, {total_wall/60:.1f} min total wall time.")
    print(f"Summary: {summary_path}")

    reasons = collections.Counter(r["stop_reason"] for r in rows if r["stop_reason"])
    if reasons:
        print("\nAgent stop reasons:")
        for reason, count in reasons.most_common():
            print(f"  {reason:24s} {count:2d}/{len(rows)}")

        # Deliberately NOT reported as "iterated as intended vs degraded".
        # An earlier version of this tally did exactly that and counted
        # `model_says_ready` as a success -- but READY on the first round means
        # no follow-up ever ran, which is C3's behaviour plus one wasted LLM
        # call. It scored 15/20 for a run whose real effect was 2/20. What
        # matters is how often a follow-up ran, and how often it changed
        # anything; `--compare` answers the second.
        iters = [r["iteration_count"] for r in rows if r["iteration_count"] != ""]
        if iters:
            single = sum(1 for i in iters if i == 1)
            print(f"\n  no follow-up ran (= previous config): {single}/{len(iters)}")
            print(f"  ran at least one follow-up         : {len(iters) - single}/{len(iters)}")
            print(f"  mean iterations                    : {sum(iters)/len(iters):.2f}")

    if args.compare:
        other = Path(args.outdir) / args.compare
        if not other.exists():
            print(f"\n--compare: {other} not found, skipping")
            return
        # The outcome-level question: did the extra work reach the answer?
        # Two configurations that retrieve differently but hand the generator
        # the same five chunks produce the same answer for the same reasons.
        changed = missing = 0
        for r in rows:
            mine = _final_sources(outdir / f"{r['id']}.txt")
            theirs = _final_sources(other / f"{r['id']}.txt")
            if theirs is None:
                missing += 1
            elif mine != theirs:
                changed += 1
        compared = len(rows) - missing
        print(f"\nVersus {args.compare} (final sources handed to the generator):")
        print(f"  changed  : {changed}/{compared}")
        print(f"  identical: {compared - changed}/{compared}")
        if missing:
            print(f"  (missing in {args.compare}: {missing})")


if __name__ == "__main__":
    main()
