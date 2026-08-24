"""Loads and validates the curated, checked-in task-id subset for a
language's agentic pilot run.

Subsets are fixed JSON files (task_subsets/task_subset_<lang>.json), not
derived at runtime, so the evaluated set is reproducible and auditable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from xrepotest.paths import get_evaluation_data_dir, get_project_root

_SUBSET_DIR = Path(__file__).parent / "task_subsets"

DEFAULT_BASELINE_MODE = "standard"
DEFAULT_BASELINE_MODEL = "claude-sonnet-4-5"


def _subset_file(language: str) -> Path:
    return _SUBSET_DIR / f"task_subset_{language}.json"


def _load_subset_data(language: str) -> Dict[str, Any]:
    path = _subset_file(language)
    if not path.exists():
        raise FileNotFoundError(f"No task subset configured for language '{language}': {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_task_ids(language: str) -> List[int]:
    data = _load_subset_data(language)
    task_ids = data.get("task_ids")
    if not isinstance(task_ids, list) or not task_ids:
        raise ValueError(
            f"Task subset file {_subset_file(language)} must contain a non-empty 'task_ids' list"
        )
    return [int(t) for t in task_ids]


def load_repo_task_ids(language: str, repo: str) -> List[int]:
    """The subset's selected task_ids for one repo (from repo_task_ids in
    the checked-in task_subset_<lang>.json, written by select_subset.py) --
    used to validate --repo/--task_id combinations in run_agentic.py."""
    data = _load_subset_data(language)
    repo_task_ids = data.get("repo_task_ids", {})
    if repo not in repo_task_ids:
        raise ValueError(
            f"repo '{repo}' has no selected tasks in {_subset_file(language)}. "
            f"Available repos: {sorted(repo_task_ids)}"
        )
    return [int(t) for t in repo_task_ids[repo]]


def load_base_dataset(language: str) -> Dict[int, Dict[str, Any]]:
    """Load <lang>_functions.jsonl indexed by task_id."""
    dataset_path = (
        get_project_root()
        / "src"
        / "xrepotest"
        / "environments"
        / "xrepotest"
        / f"{language}_functions.jsonl"
    )
    if not dataset_path.exists():
        raise FileNotFoundError(f"Base dataset not found: {dataset_path}")
    by_id: Dict[int, Dict[str, Any]] = {}
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                sample = json.loads(line)
                by_id[sample["task_id"]] = sample
    return by_id


def _baseline_task_ids_on_disk(language: str, mode: str, model: str) -> set:
    responses_path = (
        get_evaluation_data_dir() / "responses" / language / mode / model / "prompts_responses.jsonl"
    )
    if not responses_path.exists():
        raise FileNotFoundError(
            f"Baseline response file not found for fair comparison: {responses_path}"
        )
    ids = set()
    with open(responses_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                ids.add(json.loads(line).get("task_id"))
    return ids


def get_subset_samples(
    language: str,
    *,
    baseline_mode: str = DEFAULT_BASELINE_MODE,
    baseline_model: str = DEFAULT_BASELINE_MODEL,
) -> List[Dict[str, Any]]:
    """Load the configured task-id subset, cross-validate it against the base
    dataset and baseline response data, and return the full dataset samples
    (in subset order) ready for the agentic engine to consume."""
    task_ids = load_task_ids(language)
    base = load_base_dataset(language)

    missing_from_dataset = [t for t in task_ids if t not in base]
    if missing_from_dataset:
        raise ValueError(
            f"task_ids missing from {language}_functions.jsonl: {missing_from_dataset}"
        )

    baseline_ids = _baseline_task_ids_on_disk(language, baseline_mode, baseline_model)
    missing_baseline = [t for t in task_ids if t not in baseline_ids]
    if missing_baseline:
        raise ValueError(
            f"task_ids missing '{baseline_mode}/{baseline_model}' baseline data — "
            f"can't do a fair comparison for: {missing_baseline}"
        )

    return [base[t] for t in task_ids]
