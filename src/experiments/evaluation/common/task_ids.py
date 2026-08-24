"""Task ID normalization helpers shared across evaluation pipelines."""

from __future__ import annotations

from typing import Any


def normalize_task_id(task_id: Any) -> Any:
    """Normalize task_id by converting numeric strings to integers."""
    if isinstance(task_id, str):
        stripped = task_id.strip()
        if not stripped:
            return "unknown"
        try:
            return int(stripped)
        except ValueError:
            return stripped
    return task_id


def task_id_sort_key(task_id: Any) -> tuple[int, int | str]:
    """Sort numerics first, then lexicographic strings."""
    normalized = normalize_task_id(task_id)
    if isinstance(normalized, int):
        return (0, normalized)
    return (1, "" if normalized is None else str(normalized))

