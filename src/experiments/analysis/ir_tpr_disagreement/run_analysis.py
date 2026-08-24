#!/usr/bin/env python3
"""IR vs TPR Disagreement Analysis.

Computes how often the Invocation Rate (IR) check disagrees with Test Pass Rate (TPR).
A test suite "passes TPR" when compilation=true AND tests=true.
A test suite "fails IR" when invocation=false (focal function is never called).

The key metric: among TPR-passing suites, what fraction fail IR?
This reveals how much TPR alone overestimates test quality.

Usage:
    python -m experiments.analysis.ir_tpr_disagreement.run_analysis
    python -m experiments.analysis.ir_tpr_disagreement.run_analysis --results_dir path/to/results
    python -m experiments.analysis.ir_tpr_disagreement.run_analysis --lang go --mode standard
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from xrepotest.paths import get_evaluation_data_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class DisagreementStats:
    """Per-group (language / mode / model) IR-vs-TPR disagreement stats."""

    total_samples: int = 0
    total_checks: int = 0
    tpr_passing: int = 0  # compilation=true AND tests=true
    ir_failing_among_tpr: int = 0  # tpr_passing but invocation=false

    @property
    def tpr_pass_rate(self) -> float:
        if self.total_checks == 0:
            return 0.0
        return 100.0 * self.tpr_passing / self.total_checks

    @property
    def ir_disagreement_rate(self) -> float | None:
        """Fraction of TPR-passing suites that fail IR (invocation check)."""
        if self.tpr_passing == 0:
            return None
        return 100.0 * self.ir_failing_among_tpr / self.tpr_passing

    def merge(self, other: "DisagreementStats") -> "DisagreementStats":
        return DisagreementStats(
            total_samples=self.total_samples + other.total_samples,
            total_checks=self.total_checks + other.total_checks,
            tpr_passing=self.tpr_passing + other.tpr_passing,
            ir_failing_among_tpr=self.ir_failing_among_tpr + other.ir_failing_among_tpr,
        )


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def analyze_file(file_path: Path) -> DisagreementStats:
    """Parse one detailed_results.jsonl file and return disagreement stats."""
    stats = DisagreementStats()

    try:
        with file_path.open("r", encoding="utf-8") as handle:
            for line_num, line in enumerate(handle, start=1):
                payload = line.strip()
                if not payload:
                    continue

                try:
                    row = json.loads(payload)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed line %d in %s", line_num, file_path)
                    continue

                if not isinstance(row, dict):
                    continue

                stats.total_samples += 1
                checks = row.get("checks")
                if not isinstance(checks, list):
                    continue

                for check in checks:
                    if not isinstance(check, dict):
                        continue

                    stats.total_checks += 1
                    compiled = bool(check.get("compilation", False))
                    tests_pass = bool(check.get("tests", False))
                    invocation = bool(check.get("invocation", False))

                    if compiled and tests_pass:
                        stats.tpr_passing += 1
                        if not invocation:
                            stats.ir_failing_among_tpr += 1

    except OSError as exc:
        logger.error("Failed to read %s: %s", file_path, exc)

    return stats


def discover_result_files(
    results_dir: Path,
    filter_lang: str | None = None,
    filter_mode: str | None = None,
) -> dict[str, dict[str, dict[str, Path]]]:
    """Discover all detailed_results.jsonl files, organized by language/mode/model.

    Returns: {lang: {mode: {model: path}}}
    """
    discovered: dict[str, dict[str, dict[str, Path]]] = defaultdict(lambda: defaultdict(dict))

    if not results_dir.exists():
        logger.error("Results directory not found: %s", results_dir)
        return dict(discovered)

    pattern = "*/*/*/detailed_results.jsonl"
    for match in sorted(results_dir.glob(pattern)):
        rel = match.relative_to(results_dir)
        parts = rel.parts  # (lang, mode, model, filename)
        if len(parts) != 4:
            continue

        language, mode, model, _filename = parts

        if filter_lang and language != filter_lang:
            continue
        if filter_mode and mode != filter_mode:
            continue

        discovered[language][mode][model] = match

    return {lang: dict(modes) for lang, modes in discovered.items()}


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def aggregate_by_language(
    per_model: dict[str, dict[str, dict[str, DisagreementStats]]],
) -> dict[str, DisagreementStats]:
    """Roll up per-model stats into per-language totals."""
    result: dict[str, DisagreementStats] = defaultdict(DisagreementStats)
    for lang, modes in per_model.items():
        for mode, models in modes.items():
            for model, stats in models.items():
                result[lang] = result[lang].merge(stats)
    return dict(result)


def aggregate_by_language_mode(
    per_model: dict[str, dict[str, dict[str, DisagreementStats]]],
) -> dict[str, dict[str, DisagreementStats]]:
    """Roll up per-model stats into per-language-per-mode totals."""
    result: dict[str, dict[str, DisagreementStats]] = defaultdict(lambda: defaultdict(DisagreementStats))
    for lang, modes in per_model.items():
        for mode, models in modes.items():
            for model, stats in models.items():
                result[lang][mode] = result[lang][mode].merge(stats)
    return {lang: dict(modes) for lang, modes in result.items()}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def stats_to_dict(stats: DisagreementStats) -> dict[str, Any]:
    return {
        "total_samples": stats.total_samples,
        "total_checks": stats.total_checks,
        "tpr_passing": stats.tpr_passing,
        "tpr_pass_rate": round(stats.tpr_pass_rate, 2),
        "ir_failing_among_tpr": stats.ir_failing_among_tpr,
        "ir_disagreement_rate": (
            round(stats.ir_disagreement_rate, 2)
            if stats.ir_disagreement_rate is not None
            else None
        ),
    }


def generate_markdown_report(
    per_model: dict[str, dict[str, dict[str, DisagreementStats]]],
    per_lang_mode: dict[str, dict[str, DisagreementStats]],
    per_lang: dict[str, DisagreementStats],
    n_result_files: int,
) -> str:
    """Generate a human-readable markdown report."""
    lines: list[str] = []

    lines.append("# IR vs TPR Disagreement Analysis")
    lines.append("")
    lines.append(
        "**Definition:** A test suite *passes TPR* when `compilation=true` AND `tests=true`. "
        "A test suite *fails IR* when `invocation=false` (the focal function is never called). "
        "The **disagreement rate** is the fraction of TPR-passing suites that fail IR — "
        "i.e., tests that pass without actually exercising the target function."
    )
    lines.append("")
    lines.append(f"**Data source:** {n_result_files} result files across all languages/modes/models.")
    lines.append("")

    # ---- Per-language summary table ----
    lines.append("## Per-Language Summary")
    lines.append("")
    lines.append(
        "| Language | Total Checks | TPR Passing | TPR Pass Rate | IR Fail (among TPR) | Disagreement Rate |"
    )
    lines.append(
        "|----------|-------------|-------------|---------------|---------------------|-------------------|"
    )

    for lang in sorted(per_lang.keys()):
        s = per_lang[lang]
        dr = f"{s.ir_disagreement_rate:.1f}%" if s.ir_disagreement_rate is not None else "N/A"
        lines.append(
            f"| {lang} | {s.total_checks} | {s.tpr_passing} | {s.tpr_pass_rate:.1f}% | "
            f"{s.ir_failing_among_tpr} | {dr} |"
        )

    lines.append("")

    # ---- Per-language, per-mode summary ----
    lines.append("## Per-Language × Per-Mode Detail")
    lines.append("")

    for lang in sorted(per_lang_mode.keys()):
        lines.append(f"### {lang}")
        lines.append("")
        lines.append(
            "| Mode | Total Checks | TPR Passing | TPR Pass Rate | IR Fail (among TPR) | Disagreement Rate |"
        )
        lines.append(
            "|------|-------------|-------------|---------------|---------------------|-------------------|"
        )

        for mode in sorted(per_lang_mode[lang].keys()):
            s = per_lang_mode[lang][mode]
            dr = f"{s.ir_disagreement_rate:.1f}%" if s.ir_disagreement_rate is not None else "N/A"
            lines.append(
                f"| {mode} | {s.total_checks} | {s.tpr_passing} | {s.tpr_pass_rate:.1f}% | "
                f"{s.ir_failing_among_tpr} | {dr} |"
            )
        lines.append("")

    # ---- Per-model detail (collapsible) ----
    lines.append("## Per-Model Detail")
    lines.append("")

    for lang in sorted(per_model.keys()):
        lines.append(f"### {lang}")
        lines.append("")

        for mode in sorted(per_model[lang].keys()):
            lines.append(f"#### {lang} / {mode}")
            lines.append("")
            lines.append(
                "| Model | Total Checks | TPR Passing | TPR Pass Rate | IR Fail (among TPR) | Disagreement Rate |"
            )
            lines.append(
                "|-------|-------------|-------------|---------------|---------------------|-------------------|"
            )

            for model in sorted(per_model[lang][mode].keys()):
                s = per_model[lang][mode][model]
                dr = f"{s.ir_disagreement_rate:.1f}%" if s.ir_disagreement_rate is not None else "N/A"
                lines.append(
                    f"| {model} | {s.total_checks} | {s.tpr_passing} | {s.tpr_pass_rate:.1f}% | "
                    f"{s.ir_failing_among_tpr} | {dr} |"
                )
            lines.append("")

    # ---- Rebuttal paragraph ----
    lines.append("## Rebuttal Paragraph")
    lines.append("")

    # Build the rebuttal
    lang_paragraphs = []
    for lang in sorted(per_lang.keys()):
        s = per_lang[lang]
        if s.ir_disagreement_rate is not None and s.tpr_passing > 0:
            lang_paragraphs.append(
                f"**{lang}**: {s.ir_disagreement_rate:.1f}% of the {s.tpr_passing} "
                f"TPR-passing suites ({s.ir_failing_among_tpr} suites) fail the invocation check."
            )
        else:
            lang_paragraphs.append(
                f"**{lang}**: No TPR-passing suites to evaluate."
            )

    rebuttal = (
        "Across all evaluated languages, a substantial fraction of test suites that pass "
        "compilation and execution (TPR-passing) nevertheless fail the invocation check — "
        "meaning the generated test never actually calls the focal function. "
        "This demonstrates that Test Pass Rate alone is an insufficient quality signal: "
        "it overestimates meaningful test generation by counting suites that pass without "
        "exercising the target code. "
        "The Invocation Rate (IR) check captures this missing dimension, making it a "
        "necessary complement to TPR for any rigorous evaluation of unit test generation. "
        "Per-language breakdown:\n\n" + "\n".join(f"- {p}" for p in lang_paragraphs)
    )

    lines.append(rebuttal)
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="IR vs TPR Disagreement Analysis — how often do passing tests fail invocation?"
    )
    parser.add_argument(
        "--results_dir",
        type=Path,
        default=None,
        help="Path to evaluation results directory (default: auto-detect from project structure)",
    )
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=None,
        help="Output directory for reports (default: <analysis_dir>/output)",
    )
    parser.add_argument("--lang", type=str, default=None, help="Filter to specific language")
    parser.add_argument("--mode", type=str, default=None, help="Filter to specific evaluation mode")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.results_dir is None:
        args.results_dir = get_evaluation_data_dir() / "results"

    analysis_dir = Path(__file__).resolve().parent
    if args.output_dir is None:
        args.output_dir = analysis_dir / "output"

    args.output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Results directory: %s", args.results_dir)
    logger.info("Output directory: %s", args.output_dir)

    # ---- Discover ----
    discovered = discover_result_files(
        args.results_dir,
        filter_lang=args.lang,
        filter_mode=args.mode,
    )

    # ---- Analyze ----
    per_model: dict[str, dict[str, dict[str, DisagreementStats]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    n_files = 0

    for lang, modes in discovered.items():
        for mode, models in modes.items():
            for model, file_path in models.items():
                stats = analyze_file(file_path)
                per_model[lang][mode][model] = stats
                n_files += 1
                if stats.total_checks > 0 and stats.ir_disagreement_rate is not None:
                    logger.info(
                        "%s/%s/%-40s  checks=%5d  tpr=%.1f%%  ir_disagree=%.1f%%",
                        lang,
                        mode,
                        model,
                        stats.total_checks,
                        stats.tpr_pass_rate,
                        stats.ir_disagreement_rate,
                    )
                else:
                    logger.info(
                        "%s/%s/%-40s  checks=%5d  tpr=%.1f%%  ir_disagree=N/A",
                        lang,
                        mode,
                        model,
                        stats.total_checks,
                        stats.tpr_pass_rate,
                    )

    # ---- Aggregate ----
    per_lang_mode = aggregate_by_language_mode(per_model)
    per_lang = aggregate_by_language(per_model)

    # ---- Serialize ----
    # Per-model JSON
    per_model_serializable: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for lang, modes in per_model.items():
        per_model_serializable[lang] = {}
        for mode, models in modes.items():
            per_model_serializable[lang][mode] = {}
            for model, stats in models.items():
                per_model_serializable[lang][mode][model] = stats_to_dict(stats)

    # Per-language-mode JSON
    per_lang_mode_serializable: dict[str, dict[str, dict[str, Any]]] = {}
    for lang, modes in per_lang_mode.items():
        per_lang_mode_serializable[lang] = {}
        for mode, stats in modes.items():
            per_lang_mode_serializable[lang][mode] = stats_to_dict(stats)

    # Per-language JSON
    per_lang_serializable = {lang: stats_to_dict(s) for lang, s in per_lang.items()}

    combined = {
        "per_language": per_lang_serializable,
        "per_language_mode": per_lang_mode_serializable,
        "per_model": per_model_serializable,
    }

    json_path = args.output_dir / "ir_tpr_disagreement.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2)
    logger.info("Saved JSON report to %s", json_path)

    # ---- Markdown report ----
    md = generate_markdown_report(per_model, per_lang_mode, per_lang, n_files)
    md_path = args.output_dir / "ir_tpr_disagreement.md"
    with md_path.open("w", encoding="utf-8") as f:
        f.write(md)
    logger.info("Saved Markdown report to %s", md_path)

    # ---- Print key summary to stdout ----
    print()
    print("=" * 80)
    print("IR vs TPR Disagreement — Per-Language Summary")
    print("=" * 80)
    print(f"{'Language':<10} {'Checks':>7} {'TPR%':>7} {'IR Disagree%':>14} {'(fail/tpr)':>12}")
    print("-" * 50)
    for lang in sorted(per_lang.keys()):
        s = per_lang[lang]
        dr = f"{s.ir_disagreement_rate:.1f}%" if s.ir_disagreement_rate is not None else "N/A"
        ratio = f"{s.ir_failing_among_tpr}/{s.tpr_passing}" if s.tpr_passing > 0 else "0/0"
        print(f"{lang:<10} {s.total_checks:>7} {s.tpr_pass_rate:>6.1f}% {dr:>13} {ratio:>12}")
    print("=" * 80)
    print()
    print("Disagreement = fraction of TPR-passing suites that fail invocation (IR).")
    print("Higher % means TPR is a weaker signal — more 'passing' tests don't call the focal function.")
    print()


if __name__ == "__main__":
    main()
