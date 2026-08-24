"""Shared mode/model discovery helpers."""

from __future__ import annotations

from pathlib import Path


def discover_mode_model_tasks(
    lang_base_dir: Path,
    mode: str | None = None,
    model: str | None = None,
) -> list[tuple[str, str]]:
    """Discover `(mode, model)` task tuples from `data/results/{lang}`.

    Raises:
        ValueError: If requested mode/model combinations cannot be resolved.
    """
    if mode and model:
        return [(mode, model)]

    if mode:
        mode_dir = lang_base_dir / mode
        if not mode_dir.exists():
            raise ValueError(f"Mode directory not found: {mode_dir}")

        tasks = [(mode, model_path.name) for model_path in sorted(mode_dir.iterdir()) if model_path.is_dir()]
        if not tasks:
            raise ValueError(f"No models found in {mode_dir}")
        return tasks

    if model:
        tasks: list[tuple[str, str]] = []
        for mode_path in sorted(lang_base_dir.iterdir()):
            if not mode_path.is_dir():
                continue
            model_path = mode_path / model
            if model_path.exists() and model_path.is_dir():
                tasks.append((mode_path.name, model))

        if not tasks:
            raise ValueError(f"Model '{model}' not found in any mode")
        return tasks

    tasks = [
        (mode_path.name, model_path.name)
        for mode_path in sorted(lang_base_dir.iterdir())
        if mode_path.is_dir()
        for model_path in sorted(mode_path.iterdir())
        if model_path.is_dir()
    ]
    if not tasks:
        raise ValueError(f"No models found in {lang_base_dir}")
    return tasks

