"""
Command-Line Interface for Error Classification.

Usage examples:
    # Classify one detailed_results file
    python classify_errors.py --input_file path/to/detailed_results.jsonl --language rust

    # Classify a directory recursively
    python classify_errors.py --input_dir evaluation/data/results/rust --language rust

    # Filter directory processing with mode/model lists
    python classify_errors.py --input_dir evaluation/data/results/rust --language rust \
      --modes standard,file_context --models gpt-5.2,fireworks_gpt-oss-120b
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from experiments.analysis.error_analysis.analyze_api_hallucinations import (
    process_api_hallucination_breakdown,
)
from experiments.analysis.error_analysis.cli_helpers import (
    SUPPORTED_LANGUAGES,
    ClassificationTarget,
    build_single_file_target,
    combine_filter_values,
    discover_directory_targets,
)
from experiments.analysis.error_analysis.processors.batch import BatchErrorClassifier


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify errors in LLM-generated test code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input_file",
        type=str,
        help="Path to a single detailed_results.jsonl file",
    )
    input_group.add_argument(
        "--input_dir",
        type=str,
        help="Directory containing detailed_results.jsonl files (searched recursively)",
    )

    parser.add_argument(
        "--language",
        type=str,
        required=True,
        choices=SUPPORTED_LANGUAGES,
        help="Programming language of the tests",
    )

    parser.add_argument(
        "--output_dir",
        type=str,
        default=None,
        help="Output directory for error analysis results (default: same as input parent)",
    )
    parser.add_argument(
        "--summary_file",
        type=str,
        default=None,
        help="Optional path for aggregated summary JSON (default: global_summary.json under output root)",
    )

    parser.add_argument(
        "--mode",
        type=str,
        default=None,
        help="Single mode selector/metadata value (e.g., standard)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Single model selector/metadata value (e.g., gpt-5.2)",
    )
    parser.add_argument(
        "--modes",
        type=str,
        default=None,
        help="Comma-separated mode filters (directory mode) or metadata (single-file mode)",
    )
    parser.add_argument(
        "--models",
        type=str,
        default=None,
        help="Comma-separated model filters (directory mode) or metadata (single-file mode)",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed summary information",
    )

    return parser.parse_args()


def _resolve_targets(args: argparse.Namespace) -> list[ClassificationTarget]:
    mode_filters = combine_filter_values(args.mode, args.modes)
    model_filters = combine_filter_values(args.model, args.models)
    output_dir = Path(args.output_dir) if args.output_dir else None

    if args.input_file:
        target = build_single_file_target(
            input_file=Path(args.input_file),
            language=args.language,
            output_dir=output_dir,
            mode_filters=mode_filters,
            model_filters=model_filters,
        )
        return [target]

    return discover_directory_targets(
        input_dir=Path(args.input_dir),
        language=args.language,
        output_base_dir=output_dir,
        mode_filters=mode_filters,
        model_filters=model_filters,
    )


def _run_targets(
    *,
    language: str,
    targets: list[ClassificationTarget],
    verbose: bool,
) -> tuple[dict[str, dict], dict[str, str], dict[str, str]]:
    classifier = BatchErrorClassifier(language)
    summaries: dict[str, dict] = {}
    classification_failures: dict[str, str] = {}
    breakdown_failures: dict[str, str] = {}

    print(f"Language: {language}")
    print(f"Targets to process: {len(targets)}")
    print("-" * 70)

    for index, target in enumerate(targets, 1):
        label_suffix = []
        if target.mode:
            label_suffix.append(f"mode={target.mode}")
        if target.model:
            label_suffix.append(f"model={target.model}")
        label = ", ".join(label_suffix) if label_suffix else "metadata=unknown"

        print(f"\n[{index}/{len(targets)}] {target.input_file} ({label})")
        try:
            summary = classifier.process_file(str(target.input_file), str(target.output_dir))
            summaries[str(target.input_file)] = summary
        except Exception as exc:  # noqa: BLE001
            classification_failures[str(target.input_file)] = str(exc)
            print(f"[FAIL] {target.input_file}: {exc}", file=sys.stderr)
            if verbose:
                import traceback

                traceback.print_exc()
            continue

        try:
            process_api_hallucination_breakdown(
                language=language,
                error_analysis_path=target.error_analysis_path,
                detailed_results_path=target.input_file,
                output_path=target.api_breakdown_path,
                mode=target.mode,
                model=target.model,
            )
            print(f"[OK] Completed: {target.output_dir}")
        except Exception as exc:  # noqa: BLE001
            breakdown_failures[str(target.input_file)] = str(exc)
            print(
                f"[WARNING] Classification succeeded but API breakdown failed for "
                f"{target.input_file}: {exc}",
                file=sys.stderr,
            )
            if verbose:
                import traceback

                traceback.print_exc()

    return summaries, classification_failures, breakdown_failures


def print_verbose_summary(summary: dict) -> None:
    """Print detailed summary information for a single processed file."""
    print("\n" + "=" * 60)
    print("DETAILED SUMMARY")
    print("=" * 60)

    print(f"\nLanguage: {summary['language']}")
    print(f"Total Samples: {summary['total_samples']}")
    print(f"Total Tests: {summary['total_tests']}")
    avg_tests = (
        summary["total_tests"] / summary["total_samples"] if summary["total_samples"] > 0 else 0
    )
    print(f"Average Tests per Sample: {avg_tests:.2f}")

    print("\nError Statistics:")
    print(f"  Tests with Errors: {summary['tests_with_errors']} ({summary['error_rate'] * 100:.1f}%)")
    print(f"  Tests without Errors: {summary['tests_without_errors']}")
    print(
        f"  Samples with Errors: {summary['samples_with_errors']} "
        f"({summary['sample_error_rate'] * 100:.1f}%)"
    )

    print("\nError Category Breakdown:")
    for category, stats in sorted(
        summary["category_distribution"].items(),
        key=lambda item: item[1]["count"],
        reverse=True,
    ):
        pct_errors = stats.get("percentage_of_errors", stats.get("percentage", 0.0))
        pct_tests = stats.get(
            "percentage_of_total_tests",
            (stats["count"] / summary["total_tests"] * 100 if summary["total_tests"] > 0 else 0.0),
        )
        print(f"  {category}:")
        print(f"    Count: {stats['count']}")
        print(f"    Percentage of Errors: {pct_errors:.1f}%")
        print(f"    Percentage of Total Tests: {pct_tests:.1f}%")


def print_aggregate_stats(summaries: dict[str, dict]) -> None:
    """Print aggregate statistics across multiple processed files."""
    total_samples = sum(summary["total_samples"] for summary in summaries.values())
    total_tests = sum(summary["total_tests"] for summary in summaries.values())
    total_errors = sum(summary["tests_with_errors"] for summary in summaries.values())

    print(f"Files Processed: {len(summaries)}")
    print(f"Total Samples: {total_samples}")
    print(f"Total Tests: {total_tests}")
    error_rate_pct = (total_errors / total_tests * 100) if total_tests > 0 else 0.0
    print(f"Total Errors: {total_errors} ({error_rate_pct:.1f}%)")

    aggregate_categories: Counter[str] = Counter()
    for summary in summaries.values():
        for category, count in summary.get("category_counts", {}).items():
            aggregate_categories[category] += count

    print("\nAggregate Category Distribution:")
    for category, count in aggregate_categories.most_common():
        pct = count / total_errors * 100 if total_errors > 0 else 0.0
        print(f"  {category}: {count} ({pct:.1f}%)")


def _determine_summary_path(args: argparse.Namespace, targets: list[ClassificationTarget]) -> Path:
    """Resolve destination path for aggregate summary output."""
    if args.summary_file:
        return Path(args.summary_file)
    if args.output_dir:
        return Path(args.output_dir) / "global_summary.json"
    if args.input_dir:
        return Path(args.input_dir) / "global_summary.json"
    return targets[0].output_dir / "global_summary.json"


def _build_cli_summary_data(
    *, language: str, targets: list[ClassificationTarget], summaries: dict[str, dict]
) -> dict:
    """Build aggregate summary data for all successfully processed targets."""
    total_samples = 0
    total_tests = 0
    total_errors = 0
    category_counts: Counter[str] = Counter()

    mode_totals = defaultdict(
        lambda: {"targets_processed": 0, "total_samples": 0, "total_tests": 0, "total_errors": 0}
    )
    model_totals = defaultdict(
        lambda: {"targets_processed": 0, "total_samples": 0, "total_tests": 0, "total_errors": 0}
    )
    processed_targets: list[dict] = []

    for target in targets:
        key = str(target.input_file)
        summary = summaries.get(key)
        if summary is None:
            continue

        samples = int(summary.get("total_samples", 0))
        tests = int(summary.get("total_tests", 0))
        errors = int(summary.get("tests_with_errors", 0))

        total_samples += samples
        total_tests += tests
        total_errors += errors

        for category, count in summary.get("category_counts", {}).items():
            category_counts[category] += int(count)

        mode_key = target.mode or "unknown"
        model_key = target.model or "unknown"

        mode_totals[mode_key]["targets_processed"] += 1
        mode_totals[mode_key]["total_samples"] += samples
        mode_totals[mode_key]["total_tests"] += tests
        mode_totals[mode_key]["total_errors"] += errors

        model_totals[model_key]["targets_processed"] += 1
        model_totals[model_key]["total_samples"] += samples
        model_totals[model_key]["total_tests"] += tests
        model_totals[model_key]["total_errors"] += errors

        processed_targets.append(
            {
                "input_file": str(target.input_file),
                "output_dir": str(target.output_dir),
                "mode": target.mode,
                "model": target.model,
                "total_samples": samples,
                "total_tests": tests,
                "total_errors": errors,
                "error_rate": (errors / tests) if tests > 0 else 0.0,
            }
        )

    def _finalize_groups(groups: dict[str, dict[str, int]]) -> dict[str, dict]:
        finalized: dict[str, dict] = {}
        for group_name in sorted(groups):
            group = groups[group_name]
            group_tests = group["total_tests"]
            finalized[group_name] = {
                **group,
                "error_rate": (group["total_errors"] / group_tests) if group_tests > 0 else 0.0,
            }
        return finalized

    category_distribution: dict[str, dict[str, float | int]] = {}
    for category, count in sorted(category_counts.items(), key=lambda item: item[1], reverse=True):
        category_distribution[category] = {
            "count": count,
            "percentage_of_errors": (count / total_errors * 100) if total_errors > 0 else 0.0,
            "percentage_of_total_tests": (count / total_tests * 100) if total_tests > 0 else 0.0,
        }

    return {
        "language": language,
        "total_targets_processed": len(processed_targets),
        "total_samples": total_samples,
        "total_tests": total_tests,
        "total_errors": total_errors,
        "overall_error_rate": (total_errors / total_tests) if total_tests > 0 else 0.0,
        "by_mode": _finalize_groups(mode_totals),
        "by_model": _finalize_groups(model_totals),
        "category_distribution": category_distribution,
        "targets": processed_targets,
    }


def _write_cli_summary(summary_data: dict, summary_path: Path) -> None:
    """Write aggregate summary JSON for CLI execution."""
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary_data, handle, indent=2)
    print(f"\n[OK] Global summary saved to: {summary_path}")


def main() -> int:
    args = _parse_args()

    try:
        targets = _resolve_targets(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Unexpected error while resolving targets: {exc}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1

    if not targets:
        print("No files matched the requested inputs/filters.", file=sys.stderr)
        return 1

    summaries, classification_failures, breakdown_failures = _run_targets(
        language=args.language,
        targets=targets,
        verbose=args.verbose,
    )

    if not summaries:
        print("No files were processed successfully.", file=sys.stderr)
        return 1

    if args.verbose:
        if len(summaries) == 1:
            print_verbose_summary(next(iter(summaries.values())))
        else:
            print("\n" + "=" * 60)
            print("AGGREGATE STATISTICS")
            print("=" * 60)
            print_aggregate_stats(summaries)

    summary_path = _determine_summary_path(args, targets)
    cli_summary = _build_cli_summary_data(
        language=args.language,
        targets=targets,
        summaries=summaries,
    )
    _write_cli_summary(cli_summary, summary_path)

    if classification_failures:
        print(
            f"\nCompleted with failures: {len(summaries)} succeeded, "
            f"{len(classification_failures)} failed.",
            file=sys.stderr,
        )
        return 1

    if breakdown_failures:
        print(
            f"\nCompleted with warnings: API breakdown failed for "
            f"{len(breakdown_failures)} target(s).",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
