"""Recompute baseline summaries restricted to the same task-id subset as an
agentic pilot run, so the comparison is apples-to-apples (comparing a
20-30-task agentic summary against a full-dataset baseline summary would be
misleading either way, depending on whether the subset happens to be easier
or harder than average).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from experiments.evaluation.agentic.task_subset import load_task_ids
from experiments.evaluation.common.task_ids import normalize_task_id
from xrepotest.environments.base.metrics import calculate_summary
from xrepotest.paths import get_evaluation_data_dir


def _load_detailed_results(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"detailed_results.jsonl not found: {path}")
    records: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def restricted_summary(detailed_results_path: Path, task_ids: List[int]) -> Dict[str, Any]:
    task_id_set = {normalize_task_id(t) for t in task_ids}
    records = _load_detailed_results(detailed_results_path)
    subset = [r for r in records if normalize_task_id(r.get("task_id")) in task_id_set]
    found_ids = {normalize_task_id(r.get("task_id")) for r in subset}
    missing = task_id_set - found_ids

    summary = calculate_summary(subset)
    summary["_subset_task_ids_found"] = len(subset)
    summary["_subset_task_ids_expected"] = len(task_id_set)
    if missing:
        summary["_subset_task_ids_missing"] = sorted(missing, key=lambda x: (isinstance(x, str), x))
    return summary


def compare(
    language: str,
    agentic_model_dir: str,
    baseline_specs: List[Tuple[str, str, str]],
    output_path: Path,
) -> Dict[str, Any]:
    """baseline_specs: list of (mode, model_dir, label) tuples."""
    task_ids = load_task_ids(language)
    data_dir = get_evaluation_data_dir()

    result: Dict[str, Any] = {"language": language, "task_ids": task_ids}

    agentic_results_path = (
        data_dir
        / "results"
        / language
        / "agentic_claude_code"
        / agentic_model_dir
        / "detailed_results.jsonl"
    )
    try:
        result["agentic_claude_code"] = restricted_summary(agentic_results_path, task_ids)
    except FileNotFoundError as exc:
        result["agentic_claude_code"] = {"error": str(exc)}

    for mode, model_dir, label in baseline_specs:
        results_path = data_dir / "results" / language / mode / model_dir / "detailed_results.jsonl"
        try:
            result[label] = restricted_summary(results_path, task_ids)
        except FileNotFoundError as exc:
            result[label] = {"error": str(exc)}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Recompute baseline summaries restricted to the agentic pilot's task-id subset"
    )
    parser.add_argument("--lang", type=str, required=True)
    parser.add_argument("--agentic-model-dir", type=str, default="claude-sonnet-4-5")
    parser.add_argument(
        "--baseline",
        action="append",
        default=[],
        metavar="mode:model_dir:label",
        help=(
            "Repeatable. e.g. --baseline standard:claude-sonnet-4-5:standard "
            "--baseline rag_dense_ws50_k10:claude-sonnet-4-5:rag_dense"
        ),
    )
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args(argv)

    baseline_specs: List[Tuple[str, str, str]] = []
    for spec in args.baseline:
        parts = spec.split(":")
        if len(parts) != 3:
            print(f"Error: --baseline must be mode:model_dir:label, got: {spec}")
            return 1
        baseline_specs.append((parts[0], parts[1], parts[2]))

    if not baseline_specs:
        baseline_specs = [("standard", args.agentic_model_dir, "standard")]

    data_dir = get_evaluation_data_dir()
    output_path = (
        Path(args.output)
        if args.output
        else data_dir
        / "results"
        / args.lang
        / "agentic_claude_code"
        / args.agentic_model_dir
        / "subset_comparison.json"
    )

    result = compare(args.lang, args.agentic_model_dir, baseline_specs, output_path)
    print(json.dumps(result, indent=2))
    print(f"\nWritten to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
