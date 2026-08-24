from collections import defaultdict
from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_FAILED_CHECK = {"compilation": False, "tests": False, "coverage": None}


@dataclass(slots=True)
class TestResult:
    test_id: str
    passed: bool
    compiled: bool
    coverage: float | None
    function_name: str
    file_path: str


@dataclass(slots=True)
class ModelResults:
    language: str
    mode: str
    model: str
    tests: list[TestResult]
    total_samples: int

    @property
    def pass_rate(self) -> float:
        if not self.tests:
            return 0.0
        return 100.0 * sum(test.passed for test in self.tests) / len(self.tests)

    @property
    def passed_count(self) -> int:
        return sum(test.passed for test in self.tests)


class DataCollector:
    def __init__(self, results_dir: Path):
        self.results_dir = Path(results_dir)
        self.data: dict[str, dict[str, dict[str, ModelResults]]] = defaultdict(lambda: defaultdict(dict))

    def discover_result_files(
        self,
        filter_lang: str | None = None,
        filter_mode: str | None = None,
    ) -> list[tuple[Path, str, str, str]]:
        if not self.results_dir.exists():
            logger.error("Results directory not found: %s", self.results_dir)
            return []

        result_files: list[tuple[Path, str, str, str]] = []
        for detailed_results in sorted(self.results_dir.glob("*/*/*/detailed_results.jsonl")):
            language, mode, model, _ = detailed_results.relative_to(self.results_dir).parts
            if filter_lang and language != filter_lang:
                continue
            if filter_mode and mode != filter_mode:
                continue
            result_files.append((detailed_results, language, mode, model))

        logger.info("Discovered %d result files", len(result_files))
        return result_files

    def _normalize_checks(
        self,
        checks: Any,
        file_path: Path,
        line_num: int,
    ) -> list[tuple[int, dict[str, Any]]]:
        if not isinstance(checks, list) or not checks:
            logger.warning(
                "Invalid or empty checks on line %d in %s; treating as failure",
                line_num,
                file_path,
            )
            return [(0, DEFAULT_FAILED_CHECK)]

        normalized_checks = [
            (index, check)
            for index, check in enumerate(checks)
            if isinstance(check, dict)
        ]
        if normalized_checks:
            return normalized_checks

        logger.warning(
            "No valid check entries on line %d in %s; treating as failure",
            line_num,
            file_path,
        )
        return [(0, DEFAULT_FAILED_CHECK)]

    def _extract_coverage(self, coverage_stats: list[Any], index: int) -> float | None:
        if index >= len(coverage_stats):
            return None

        coverage_data = coverage_stats[index]
        if not isinstance(coverage_data, dict):
            return None

        line_coverage = coverage_data.get("line_coverage")
        if isinstance(line_coverage, (float, int)):
            return float(line_coverage)
        return None

    def load_detailed_results(self, file_path: Path) -> list[TestResult]:
        tests: list[TestResult] = []

        try:
            with file_path.open("r", encoding="utf-8") as handle:
                for line_num, line in enumerate(handle, start=1):
                    payload = line.strip()
                    if not payload:
                        continue

                    try:
                        row = json.loads(payload)
                    except json.JSONDecodeError as error:
                        logger.warning("Failed to parse line %d in %s: %s", line_num, file_path, error)
                        continue

                    if not isinstance(row, dict):
                        logger.warning("Skipping line %d in %s: row is not a JSON object", line_num, file_path)
                        continue

                    function_name = str(row.get("function_name", ""))
                    source_path = str(row.get("file_path", ""))
                    test_prefix = f"{source_path}::{function_name}"

                    checks = self._normalize_checks(row.get("checks"), file_path, line_num)
                    coverage_stats = row.get("coverage_stats")
                    coverage_list = coverage_stats if isinstance(coverage_stats, list) else []

                    for index, check in checks:
                        tests.append(
                            TestResult(
                                test_id=f"{test_prefix}[{index}]",
                                passed=bool(check.get("tests", False)),
                                compiled=bool(check.get("compilation", False)),
                                coverage=self._extract_coverage(coverage_list, index),
                                function_name=function_name,
                                file_path=source_path,
                            )
                        )
        except OSError as error:
            logger.error("Error loading %s: %s", file_path, error)
            return []

        return tests

    def _load_total_samples(self, summary_path: Path, fallback: int) -> int:
        if not summary_path.exists():
            return fallback

        try:
            with summary_path.open("r", encoding="utf-8") as handle:
                summary = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            logger.warning("Failed to read %s: %s", summary_path, error)
            return fallback

        if not isinstance(summary, dict):
            return fallback

        total_samples = summary.get("total_samples", fallback)
        if isinstance(total_samples, int):
            return total_samples
        return fallback

    def collect_all_results(
        self,
        filter_lang: str | None = None,
        filter_mode: str | None = None,
        min_tests: int = 50,
    ) -> None:
        result_files = self.discover_result_files(filter_lang, filter_mode)
        loaded = 0
        skipped = 0

        for file_path, language, mode, model in result_files:
            tests = self.load_detailed_results(file_path)
            if len(tests) < min_tests:
                logger.warning(
                    "Skipping %s/%s/%s: only %d tests (min: %d)",
                    language,
                    mode,
                    model,
                    len(tests),
                    min_tests,
                )
                skipped += 1
                continue

            model_results = ModelResults(
                language=language,
                mode=mode,
                model=model,
                tests=tests,
                total_samples=self._load_total_samples(file_path.parent / "summary.json", len(tests)),
            )
            self.data[language][mode][model] = model_results
            loaded += 1

        logger.info("Loading complete: %d models loaded, %d skipped", loaded, skipped)

    def get_results(self, language: str, mode: str, model: str) -> ModelResults | None:
        return self.data.get(language, {}).get(mode, {}).get(model)

    def get_all_languages(self) -> list[str]:
        return sorted(self.data.keys())

    def get_modes_for_language(self, language: str) -> list[str]:
        return sorted(self.data.get(language, {}).keys())

    def get_models_for_language_mode(self, language: str, mode: str) -> list[str]:
        return sorted(self.data.get(language, {}).get(mode, {}).keys())

    def get_summary(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "total_languages": len(self.data),
            "total_combinations": 0,
            "languages": {},
        }

        for language, mode_data in self.data.items():
            mode_breakdown = {mode: len(models) for mode, models in mode_data.items()}
            total_models = sum(mode_breakdown.values())
            summary["languages"][language] = {
                "modes": len(mode_data),
                "total_models": total_models,
                "mode_breakdown": mode_breakdown,
            }
            summary["total_combinations"] += total_models

        return summary
