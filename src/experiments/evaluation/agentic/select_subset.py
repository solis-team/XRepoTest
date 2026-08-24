#!/usr/bin/env python3
"""Stratified, seeded subset selection for the agentic pilot.

For each repo in a language's base dataset, samples up to `easy_per_repo`
tasks where the baseline (standard/claude-sonnet-4-5 by default) already
passes (compile+tests+invocation) and up to `hard_per_repo` where it
doesn't -- so the pilot both checks for regressions on easy cases and
measures rescue rate on hard ones, without letting one large repo dominate
the subset.

This is a one-off generator, run by hand to (re)produce a checked-in
task_subset_<lang>.json; task_subset.py loads that fixed file at pipeline
runtime and does not call back into this script.

Usage:
    python select_subset.py --lang go
    python select_subset.py --lang rust --easy-per-repo 5 --hard-per-repo 5 --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from experiments.evaluation.agentic.task_subset import (
    DEFAULT_BASELINE_MODE,
    DEFAULT_BASELINE_MODEL,
    load_base_dataset,
)
from xrepotest.paths import get_evaluation_data_dir

_SUBSET_DIR = Path(__file__).parent / "task_subsets"


def _repo_of(file_path: str) -> str:
    return file_path.split("/", 1)[0]


def _load_baseline_outcomes(language: str, mode: str, model: str) -> Dict[int, bool]:
    path = get_evaluation_data_dir() / "results" / language / mode / model / "detailed_results.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Baseline detailed_results.jsonl not found: {path}")
    outcomes: Dict[int, bool] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            checks = rec.get("checks") or [{}]
            c = checks[0] if checks else {}
            passed = bool(c.get("compilation")) and bool(c.get("tests")) and bool(c.get("invocation"))
            outcomes[rec["task_id"]] = passed
    return outcomes


def select_subset(
    language: str,
    *,
    easy_per_repo: int,
    hard_per_repo: int,
    seed: int,
    baseline_mode: str = DEFAULT_BASELINE_MODE,
    baseline_model: str = DEFAULT_BASELINE_MODEL,
) -> Dict[str, Any]:
    base = load_base_dataset(language)
    outcomes = _load_baseline_outcomes(language, baseline_mode, baseline_model)

    by_repo: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: {"easy": [], "hard": []})
    for task_id, sample in base.items():
        if task_id not in outcomes:
            continue  # no baseline data on disk -- can't do a fair comparison, skip
        repo = _repo_of(sample["file_path"])
        bucket = "easy" if outcomes[task_id] else "hard"
        by_repo[repo][bucket].append(task_id)

    rng = random.Random(seed)
    selected: List[int] = []
    per_repo_report: Dict[str, Dict[str, Any]] = {}
    repo_task_ids: Dict[str, List[int]] = {}
    for repo in sorted(by_repo):
        easy_pool = sorted(by_repo[repo]["easy"])
        hard_pool = sorted(by_repo[repo]["hard"])
        rng.shuffle(easy_pool)
        rng.shuffle(hard_pool)
        easy_pick = easy_pool[:easy_per_repo]
        hard_pick = hard_pool[:hard_per_repo]
        selected.extend(easy_pick)
        selected.extend(hard_pick)
        repo_task_ids[repo] = sorted(easy_pick + hard_pick)
        per_repo_report[repo] = {
            "easy_available": len(easy_pool),
            "easy_selected": len(easy_pick),
            "hard_available": len(hard_pool),
            "hard_selected": len(hard_pick),
        }

    selected.sort()
    return {
        "language": language,
        "note": (
            f"Stratified pilot subset for the agentic evaluation mode. Per repo, up to "
            f"{easy_per_repo} tasks where {baseline_mode}/{baseline_model} already passes "
            f"(compile+tests+invocation) and up to {hard_per_repo} where it fails, seeded "
            f"random sample (seed={seed}) via select_subset.py. Repos supplying fewer than "
            f"the target count in either bucket contribute all they have -- see "
            f"per_repo_selection for the shortfall. `repo_task_ids` maps each repo to its "
            f"selected task_ids for --repo/--task_id validation in run_agentic.py."
        ),
        "seed": seed,
        "easy_per_repo": easy_per_repo,
        "hard_per_repo": hard_per_repo,
        "baseline_mode": baseline_mode,
        "baseline_model": baseline_model,
        "per_repo_selection": per_repo_report,
        "repo_task_ids": repo_task_ids,
        "task_ids": selected,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Select a stratified, per-repo agentic pilot subset"
    )
    parser.add_argument("--lang", required=True)
    parser.add_argument("--easy-per-repo", type=int, default=5)
    parser.add_argument("--hard-per-repo", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--baseline-mode", default=DEFAULT_BASELINE_MODE)
    parser.add_argument("--baseline-model", default=DEFAULT_BASELINE_MODEL)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args(argv)

    result = select_subset(
        args.lang,
        easy_per_repo=args.easy_per_repo,
        hard_per_repo=args.hard_per_repo,
        seed=args.seed,
        baseline_mode=args.baseline_mode,
        baseline_model=args.baseline_model,
    )

    output_path = Path(args.output) if args.output else _SUBSET_DIR / f"task_subset_{args.lang}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    print(f"\nSelected {len(result['task_ids'])} task_ids -> {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
