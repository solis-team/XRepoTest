#!/usr/bin/env python3
"""Host-side CLI entrypoint for the agentic (headless Claude Code) evaluation mode.

Runs Claude Code directly on this host against a scratch copy of each
repo's selected tasks, using the existing per-language production Docker
images purely as an invoked compile/test tool (see CLAUDE.md instructions
built by prompt_builder.py). All of a repo's selected tasks share a single
claude session (one repo-exploration cost instead of one per function);
--concurrency controls how many repos run at once. Output lands in
the exact prompts_responses.jsonl shape every other mode produces, so it
flows through the unmodified `xrepotest preprocess` / `xrepotest eval`
pipeline.

Usage:
    python run_agentic.py --lang go
    python run_agentic.py --lang rust --concurrency 2 --timeout 600

Output:
    data/responses/<lang>/agentic_claude_code/<model>/prompts_responses.jsonl
    data/responses/<lang>/agentic_claude_code/<model>/agentic_meta.jsonl
"""

from __future__ import annotations

import argparse
import sys

from experiments.evaluation.agentic.engine import (
    DEFAULT_MAX_WORKERS,
    DEFAULT_TIMEOUT_S,
    AgenticEngine,
)
from experiments.evaluation.agentic.language_conventions import AGENTIC_SUPPORTED_LANGUAGES
from experiments.evaluation.agentic.task_subset import (
    DEFAULT_BASELINE_MODE,
    DEFAULT_BASELINE_MODEL,
    get_subset_samples,
    load_repo_task_ids,
)
from xrepotest.paths import get_evaluation_data_dir

MODE_NAME = "agentic_claude_code"


def _parse_task_ids(raw: str) -> set:
    return {int(t.strip()) for t in raw.split(",") if t.strip()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the agentic (headless Claude Code) evaluation mode for xrepotest"
    )
    parser.add_argument(
        "--lang",
        type=str,
        required=True,
        choices=list(AGENTIC_SUPPORTED_LANGUAGES),
        help="Programming language",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=(
            "Model for the claude CLI --model flag (alias like 'sonnet' or a full model "
            "name). Omit to use the CLI's own ambient default — this repo's baseline "
            "mode/model folder names (e.g. 'claude-sonnet-4-5') are Fireworks-proxy "
            "aliases, not valid values for the natively authenticated claude CLI."
        ),
    )
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_MAX_WORKERS, help="Concurrent agent tasks"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_S,
        metavar="SECONDS",
        help="Wall-clock timeout per batch session (seconds)",
    )
    parser.add_argument(
        "--baseline-mode",
        type=str,
        default=DEFAULT_BASELINE_MODE,
        help="Baseline mode used to validate the subset has comparable data on disk",
    )
    parser.add_argument(
        "--baseline-model",
        type=str,
        default=DEFAULT_BASELINE_MODEL,
        help="Baseline model used to validate the subset has comparable data on disk",
    )
    parser.add_argument(
        "--output-model-dir",
        type=str,
        default=None,
        help="Override the output model folder name (default: sanitized --model)",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help=(
            "Only run this repo's selected tasks (from repo_task_ids in "
            "task_subsets/task_subset_<lang>.json, written by select_subset.py). "
            "All of the repo's selected tasks share a single claude session. "
            "Omit to run every repo in the subset."
        ),
    )
    parser.add_argument(
        "--task-id",
        type=str,
        default=None,
        help=(
            "Comma-separated list of explicit task_ids to run, e.g. '2,6'. Must be a "
            "subset of --repo's selected task_ids if --repo is given, otherwise must be "
            "in the configured subset for --lang. Omit to run all of --repo (or the "
            "whole subset if --repo is also omitted)."
        ),
    )
    args = parser.parse_args(argv)

    model_dir = args.output_model_dir or (
        args.model.replace("/", "_").replace(":", "_") if args.model else "default"
    )

    data_dir = get_evaluation_data_dir()
    output_dir = data_dir / "responses" / args.lang / MODE_NAME / model_dir
    output_path = output_dir / "prompts_responses.jsonl"
    meta_path = output_dir / "agentic_meta.jsonl"

    print(f"{'=' * 80}")
    print("Running xrepotest Agentic Evaluation")
    print(f"  Language:      {args.lang}")
    print(f"  Model:         {args.model or '(CLI default)'}")
    print(f"  Concurrency:   {args.concurrency}")
    print(f"  Timeout:       {args.timeout}s")
    print(f"  Output:        {output_path}")
    print(f"{'=' * 80}\n")

    try:
        samples = get_subset_samples(
            args.lang,
            baseline_mode=args.baseline_mode,
            baseline_model=args.baseline_model,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1

    if args.repo:
        try:
            allowed_ids = set(load_repo_task_ids(args.lang, args.repo))
        except (FileNotFoundError, ValueError) as exc:
            print(f"Error: {exc}")
            return 1

        if args.task_id:
            wanted = _parse_task_ids(args.task_id)
            not_selected = wanted - allowed_ids
            if not_selected:
                print(
                    f"Error: task_id(s) {sorted(not_selected)} are not in the selected "
                    f"subset for repo '{args.repo}'. Selected: {sorted(allowed_ids)}"
                )
                return 1
        else:
            wanted = allowed_ids

        samples = [s for s in samples if s.get("task_id") in wanted]

    elif args.task_id:
        wanted = _parse_task_ids(args.task_id)
        samples = [s for s in samples if s.get("task_id") in wanted]
        missing = wanted - {s.get("task_id") for s in samples}
        if missing:
            print(f"Error: task_id(s) not in the configured subset for --lang {args.lang}: {sorted(missing)}")
            return 1

    print(f"  Tasks selected: {len(samples)}\n")

    engine = AgenticEngine(
        language=args.lang,
        model=args.model,
        max_workers=args.concurrency,
        task_timeout_s=args.timeout,
        meta_output_path=meta_path,
    )
    engine.run(samples, output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
