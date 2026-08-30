"""Command-line entry point for the RAG pipeline.

    python -m rag configs                 list C0-C5 and what each enables
    python -m rag index --config C0       chunk, embed and index the corpus
    python -m rag ask "question"          answer one question
    python -m rag doctor                  check the pieces are reachable

Run inside the container so the paths and services match the rest of the system:

    docker compose exec api python -m rag index
    docker compose exec api python -m rag ask "What is the intake for Computer Engineering?"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from rag.config import (
    ABLATION_ORDER,
    CONFIGURATIONS,
    CONTROL_ORDER,
    get_config,
    implemented_configs,
)


def _corpus_dir() -> Path:
    return Path(os.environ.get("CORPUS_DIR", "./corpus"))


# ---------------------------------------------------------------------------


def cmd_configs(_args: argparse.Namespace) -> int:
    built = set(implemented_configs())
    print("Pipeline configurations")
    print("=" * 72)
    for name in ABLATION_ORDER:
        config = CONFIGURATIONS[name]
        status = "built" if name in built else "not built yet"
        print(f"\n{name}  ({status})")
        print(f"    {config.description}")
        enabled = config.innovations_enabled
        print(
            f"    innovations: {', '.join(enabled) if enabled else 'none — this is the baseline'}"
        )
        print(
            f"    chunking={config.chunking.value} retrieval={config.retrieval.value} "
            f"top_k={config.dense_top_k} citations={config.enforce_citations}"
        )
    for name in CONTROL_ORDER:
        config = CONFIGURATIONS[name]
        status = "built" if name in built else "not built yet"
        print(f"\n{name}  ({status})  [control, not an ablation step]")
        print(f"    {config.description}")
        print(
            f"    chunking={config.chunking.value} retrieval={config.retrieval.value} "
            f"top_k={config.dense_top_k} citations={config.enforce_citations}"
        )

    print("\nEach configuration adds exactly one thing to the one before it, so a")
    print("difference between two runs is attributable to that one thing —")
    print("except C0 -> C1, which also turns on the grounding prompt. C1-CONTROL")
    print("is the run that separates those two, and is not a stage of the system.")
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    """Check every piece the pipeline needs, and say what to do about each."""
    from rag.factory import build_embedder, build_generator, build_index

    ok = True

    corpus = _corpus_dir() / "normalised"
    count = len(list(corpus.glob("*.json"))) if corpus.exists() else 0
    if count:
        print(f"  PASS  corpus: {count} normalised documents in {corpus}")
    else:
        ok = False
        print(
            f"  FAIL  corpus: no documents in {corpus} — run `python -m rag.ingestion parse`"
        )

    try:
        embedder = build_embedder()
        print(
            f"  PASS  embedder configured: {embedder.model_name} ({embedder.dimension}d)"
        )
    except Exception as exc:  # noqa: BLE001 - report, do not abort the other checks
        ok = False
        print(f"  FAIL  embedder: {exc}")
        embedder = None

    if embedder is not None:
        try:
            index = build_index(embedder.model_name)
            print(f"  PASS  index reachable: {index.name}, {index.count()} vectors")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"  FAIL  index: {exc}")

    generator = build_generator()
    available, reason = generator.is_available()  # type: ignore[attr-defined]
    if available:
        print(f"  PASS  generator: {generator.model_name} ready")
    else:
        ok = False
        print(f"  FAIL  generator: {reason}")

    print("\nready" if ok else "\nnot ready — fix the FAIL lines above")
    return 0 if ok else 1


def cmd_index(args: argparse.Namespace) -> int:
    from rag.factory import build_pipeline
    from rag.ingestion.manifest import load_documents

    config = get_config(args.config)
    documents = load_documents(_corpus_dir() / "normalised")
    if not documents:
        print(
            "No normalised documents found. Run `python -m rag.ingestion parse`.",
            file=sys.stderr,
        )
        return 1

    if args.limit:
        documents = documents[: args.limit]

    pipeline = build_pipeline(config)

    if args.reset:
        print("resetting the index")
        pipeline.index.reset()
        # The sparse index must be reset with it, never separately. RRF fuses
        # dense and sparse hits by chunk_id, and chunk ids are freshly random
        # per run, so a rebuilt dense index beside a surviving sparse one
        # shares no ids with it: fusion silently degenerates into two
        # concatenated lists, no chunk ever gets the "ranked well in both"
        # boost, and C2's entire mechanism stops working without erroring.
        if pipeline.sparse_index is not None:
            print("resetting the sparse index")
            pipeline.sparse_index.reset()

    real = sum(1 for d in documents if not d.is_demo)
    print(f"config     : {config.name} — {config.description}")
    print(
        f"embedder   : {pipeline.embedder.model_name} ({pipeline.embedder.dimension}d)"
    )
    print(f"index      : {pipeline.index.name}")
    print(f"documents  : {len(documents)} ({real} real, {len(documents) - real} demo)")
    print(
        f"chunker    : {pipeline.chunker.name} "
        f"size={config.chunk_size_chars} overlap={config.chunk_overlap_chars}\n"
    )

    report = pipeline.index_documents(documents)
    print(report.summary())
    print(f"index now holds {pipeline.index.count()} vectors")

    if report.indexed != report.chunks:
        print(
            f"\nWARNING: produced {report.chunks} chunks but indexed {report.indexed}. "
            f"The index does not match the corpus.",
            file=sys.stderr,
        )
        return 1
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    from rag.factory import build_pipeline

    pipeline = build_pipeline(get_config(args.config))

    if pipeline.index.count() == 0:
        print("The index is empty. Run `python -m rag index` first.", file=sys.stderr)
        return 1

    answer = pipeline.ask(args.question)
    print(answer.format())

    if args.json:
        import json

        print("\n" + json.dumps(answer.to_log(), indent=2))
    return 0


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m rag",
        description="Retrieval-augmented generation over the institutional corpus.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    configs = sub.add_parser("configs", help="List C0-C5 and what each enables")
    configs.set_defaults(func=cmd_configs)

    doctor = sub.add_parser(
        "doctor", help="Check corpus, embedder, index and generator"
    )
    doctor.set_defaults(func=cmd_doctor)

    index = sub.add_parser("index", help="Chunk, embed and index the corpus")
    index.add_argument("--config", default="C0")
    index.add_argument("--reset", action="store_true", help="Empty the index first")
    index.add_argument(
        "--limit", type=int, default=0, help="Index only the first N documents"
    )
    index.set_defaults(func=cmd_index)

    ask = sub.add_parser("ask", help="Answer one question")
    ask.add_argument("question")
    ask.add_argument("--config", default="C0")
    ask.add_argument("--json", action="store_true", help="Also print the retrieval log")
    ask.set_defaults(func=cmd_ask)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except NotImplementedError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 2
    except KeyError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
