#!/usr/bin/env python3
import argparse
from collections import defaultdict
import json
import logging
from pathlib import Path
from typing import Any

from experiments.analysis.significance_analysis.bootstrap import BootstrapAnalyzer
from experiments.analysis.significance_analysis.data_collector import DataCollector, ModelResults
from experiments.analysis.significance_analysis.mcnemar import McNemarAnalyzer
from experiments.analysis.significance_analysis.rebuttal_generator import RebuttalGenerator
from experiments.analysis.significance_analysis.stats_utils import McNemarResult
from xrepotest.paths import get_evaluation_data_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Statistical Significance Analysis for Low-TPR Code Generation"
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
        default=Path("./output"),
        help="Path to output directory for generated files",
    )

    parser.add_argument(
        "--filter_lang",
        type=str,
        help="Filter to specific language",
    )
    parser.add_argument(
        "--filter_mode",
        type=str,
        help="Filter to specific evaluation mode",
    )

    parser.add_argument(
        "--min_tests",
        type=int,
        default=50,
        help="Minimum number of tests required (default: 50)",
    )
    parser.add_argument(
        "--n_iterations",
        type=int,
        default=10000,
        help="Number of bootstrap iterations (default: 10000)",
    )
    parser.add_argument(
        "--top_n",
        type=int,
        default=3,
        help="Number of top models to compare (default: 3)",
    )
    parser.add_argument(
        "--confidence_level",
        type=float,
        default=0.95,
        help="Confidence level for bootstrap CI (default: 0.95)",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.05,
        help="Significance level for McNemar test (default: 0.05)",
    )

    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Show available data without running analysis",
    )
    parser.add_argument(
        "--skip_bootstrap",
        action="store_true",
        help="Skip bootstrap analysis",
    )
    parser.add_argument(
        "--skip_mcnemar",
        action="store_true",
        help="Skip McNemar test",
    )
    return parser.parse_args()


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def serialize_mcnemar_results(results: list[McNemarResult]) -> list[dict[str, object]]:
    return [result.to_dict() for result in results]


def get_models_data(
    collector: DataCollector,
    language: str,
    mode: str,
) -> dict[str, ModelResults]:
    models_data: dict[str, ModelResults] = {}
    for model in collector.get_models_for_language_mode(language, mode):
        model_result = collector.get_results(language, mode, model)
        if model_result is not None:
            models_data[model] = model_result
    return models_data


def analyze_language_mode(
    collector: DataCollector,
    language: str,
    mode: str,
    bootstrap_analyzer: BootstrapAnalyzer,
    mcnemar_analyzer: McNemarAnalyzer,
    skip_bootstrap: bool,
    skip_mcnemar: bool,
    top_n: int,
) -> tuple[list[dict[str, object]], list[McNemarResult]]:
    models_data = get_models_data(collector, language, mode)
    if not models_data:
        return [], []

    bootstrap_results: list[dict[str, object]] = []
    if not skip_bootstrap:
        intervals = bootstrap_analyzer.analyze_all_models(models_data, show_progress=True)
        bootstrap_results = bootstrap_analyzer.get_summary_table(models_data, intervals)

    mcnemar_results: list[McNemarResult] = []
    if not skip_mcnemar and len(models_data) >= 2:
        mcnemar_results = mcnemar_analyzer.compare_top_models(models_data, top_n=top_n)

    return bootstrap_results, mcnemar_results


def serialize_cross_mode(results: list[McNemarResult]) -> list[dict[str, object]]:
    serialized = []
    for result in results:
        model_name = result.model_a.split("@", maxsplit=1)[0]
        serialized.append(
            {
                "model": model_name,
                "mode_a": "standard",
                "mode_b": "file_context",
                "n_tests": result.n_tests,
                "standard_only": result.a_only,
                "file_context_only": result.b_only,
                "both_pass": result.both_pass,
                "both_fail": result.both_fail,
                "chi_square": result.chi_square,
                "p_value": result.p_value,
                "significant": result.significant,
            }
        )
    return serialized


def main() -> None:
    args = parse_args()
    # Default results_dir to project evaluation data if not provided
    if args.results_dir is None:
        args.results_dir = get_evaluation_data_dir() / "results"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Results directory: %s", args.results_dir)
    logger.info("Output directory: %s", args.output_dir)

    collector = DataCollector(args.results_dir)

    collector.collect_all_results(
        filter_lang=args.filter_lang,
        filter_mode=args.filter_mode,
        min_tests=args.min_tests,
    )

    summary = collector.get_summary()
    save_json(args.output_dir / "data_summary.json", summary)

    if args.dry_run:
        logger.info("Dry run complete")
        return

    bootstrap_analyzer = BootstrapAnalyzer(
        n_iterations=args.n_iterations,
        confidence_level=args.confidence_level,
    )
    mcnemar_analyzer = McNemarAnalyzer(
        alpha=args.alpha,
        correction="bonferroni",
    )
    rebuttal_generator = RebuttalGenerator()

    all_bootstrap_results: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(dict)
    all_mcnemar_results: dict[str, dict[str, list[McNemarResult]]] = defaultdict(dict)

    for language in collector.get_all_languages():
        for mode in collector.get_modes_for_language(language):
            logger.info("Analyzing %s/%s", language, mode)
            bootstrap_table, mcnemar_results = analyze_language_mode(
                collector=collector,
                language=language,
                mode=mode,
                bootstrap_analyzer=bootstrap_analyzer,
                mcnemar_analyzer=mcnemar_analyzer,
                skip_bootstrap=args.skip_bootstrap,
                skip_mcnemar=args.skip_mcnemar,
                top_n=args.top_n,
            )

            if bootstrap_table:
                all_bootstrap_results[language][mode] = bootstrap_table
                save_json(args.output_dir / "bootstrap" / language / mode / "results.json", bootstrap_table)

            if mcnemar_results:
                all_mcnemar_results[language][mode] = mcnemar_results
                save_json(
                    args.output_dir / "mcnemar" / language / mode / "results.json",
                    serialize_mcnemar_results(mcnemar_results),
                )

    if not args.skip_mcnemar:
        for language in collector.get_all_languages():
            modes = set(collector.get_modes_for_language(language))
            if {"standard", "file_context"} - modes:
                continue

            standard_models = get_models_data(collector, language, "standard")
            file_context_models = get_models_data(collector, language, "file_context")
            cross_mode_results = mcnemar_analyzer.compare_cross_mode(
                standard_models,
                file_context_models,
                "standard",
                "file_context",
            )
            if not cross_mode_results:
                continue

            save_json(
                args.output_dir / "mcnemar_cross_mode" / language / "standard_vs_file_context.json",
                serialize_cross_mode(cross_mode_results),
            )

    serialized_mcnemar = {
        language: {
            mode: serialize_mcnemar_results(results)
            for mode, results in mode_data.items()
        }
        for language, mode_data in all_mcnemar_results.items()
    }
    save_json(
        args.output_dir / "combined_summary.json",
        {
            "bootstrap": dict(all_bootstrap_results),
            "mcnemar": serialized_mcnemar,
        },
    )

    rebuttal_text = rebuttal_generator.generate_rebuttal_paragraph(
        dict(all_bootstrap_results),
        dict(all_mcnemar_results),
        n_bootstrap_iterations=args.n_iterations,
    )
    rebuttal_generator.save_rebuttal(
        rebuttal_text,
        args.output_dir / "rebuttal.md",
    )
    logger.info("Analysis complete. Output directory: %s", args.output_dir)


if __name__ == "__main__":
    main()
