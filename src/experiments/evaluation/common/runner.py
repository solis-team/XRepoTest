"""Shared mode/model runner helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence


ModeModelTask = tuple[str, str]
SkippedModeModelTask = tuple[str, str, str]


def task_label(mode: str, model: str) -> str:
    """Build display label for a mode/model task."""
    return f"{mode}/{model}"


def print_discovery_intro(
    *,
    mode: str | None,
    model: str | None,
    lang_base_dir: Path,
    eval_dir: Path,
) -> None:
    """Print common discovery intro banner."""
    if mode and model:
        print(f"🔍 Using explicit mode/model: {mode}/{model}")
    elif mode:
        print(f"🔍 Scanning for models in {mode} mode...")
    elif model:
        print(f"🔍 Scanning for '{model}' across all modes...")
    else:
        print(
            f"🔍 Scanning for all modes and models in "
            f"{lang_base_dir.relative_to(eval_dir)}..."
        )


def print_discovery_count(
    *,
    mode: str | None,
    model: str | None,
    task_count: int,
) -> None:
    """Print common discovery count summary."""
    if mode and not model:
        print(f"   Found {task_count} model(s)\n")
    elif model and not mode:
        print(f"   Found in {task_count} mode(s)\n")
    elif not mode and not model:
        print(f"   Found {task_count} mode/model combination(s)\n")
    else:
        print()


def print_mode_model_summary(
    *,
    title: str,
    success_label: str,
    success_items: Sequence[ModeModelTask],
    skipped_items: Sequence[SkippedModeModelTask],
    failed_items: Sequence[ModeModelTask],
) -> int:
    """Print common summary block and return process exit code."""
    print(f"\n{'='*80}")
    print(title)
    print(f"{'='*80}")
    print(f"✅ {success_label}: {len(success_items)}")
    for mode, model in success_items:
        print(f"   - {task_label(mode, model)}")

    if skipped_items:
        print(f"\n⏭️  Skipped: {len(skipped_items)}")
        for mode, model, reason in skipped_items:
            print(f"   - {task_label(mode, model)} ({reason})")

    if failed_items:
        print(f"\n❌ Failed: {len(failed_items)}")
        for mode, model in failed_items:
            print(f"   - {task_label(mode, model)}")

    print(f"{'='*80}\n")
    return 1 if failed_items else 0

