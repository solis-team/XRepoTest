import logging
from typing import Iterable

import numpy as np
from tqdm import tqdm  # type: ignore[import-untyped]

from experiments.analysis.significance_analysis.data_collector import ModelResults
from experiments.analysis.significance_analysis.stats_utils import ConfidenceInterval

logger = logging.getLogger(__name__)


class BootstrapAnalyzer:
    def __init__(self, n_iterations: int = 10000, confidence_level: float = 0.95, random_seed: int = 42):
        if n_iterations <= 0:
            raise ValueError("n_iterations must be > 0")
        if not 0 < confidence_level < 1:
            raise ValueError("confidence_level must be in (0, 1)")

        self.n_iterations = n_iterations
        self.confidence_level = confidence_level
        self.rng = np.random.RandomState(random_seed)

    def bootstrap_pass_rate(self, test_results: list[bool]) -> np.ndarray:
        if not test_results:
            return np.array([], dtype=float)

        n_tests = len(test_results)
        test_array = np.array(test_results, dtype=bool)
        bootstrap_rates = np.zeros(self.n_iterations, dtype=float)

        for iteration in range(self.n_iterations):
            sample_indices = self.rng.randint(0, n_tests, size=n_tests)
            bootstrap_rates[iteration] = 100.0 * np.mean(test_array[sample_indices])

        return bootstrap_rates

    def compute_confidence_interval(self, bootstrap_rates: np.ndarray) -> ConfidenceInterval:
        if bootstrap_rates.size == 0:
            return ConfidenceInterval(lower=0.0, upper=0.0, mean=0.0, std=0.0)

        alpha = 1 - self.confidence_level
        lower = np.percentile(bootstrap_rates, 100 * (alpha / 2))
        upper = np.percentile(bootstrap_rates, 100 * (1 - alpha / 2))
        mean = np.mean(bootstrap_rates)
        std = np.std(bootstrap_rates, ddof=1)

        return ConfidenceInterval(
            lower=float(lower),
            upper=float(upper),
            mean=float(mean),
            std=float(std),
        )

    def analyze_model(self, model_results: ModelResults) -> ConfidenceInterval:
        outcomes = [test.passed for test in model_results.tests]
        if not outcomes:
            logger.warning("No test results for %s", model_results.model)
            return ConfidenceInterval(lower=0.0, upper=0.0, mean=0.0, std=0.0)
        return self.compute_confidence_interval(self.bootstrap_pass_rate(outcomes))

    def analyze_all_models(
        self,
        models_data: dict[str, ModelResults],
        show_progress: bool = True,
    ) -> dict[str, ConfidenceInterval]:
        model_items: Iterable[tuple[str, ModelResults]] = models_data.items()
        if show_progress:
            model_items = tqdm(model_items, desc="Bootstrap analysis")

        return {
            model_name: self.analyze_model(model_results)
            for model_name, model_results in model_items
        }

    def get_summary_table(
        self,
        models_data: dict[str, ModelResults],
        bootstrap_results: dict[str, ConfidenceInterval],
    ) -> list[dict[str, object]]:
        table_data: list[dict[str, object]] = []

        for model_name in sorted(bootstrap_results, key=lambda key: bootstrap_results[key].mean, reverse=True):
            model_result = models_data[model_name]
            confidence_interval = bootstrap_results[model_name]
            table_data.append(
                {
                    "model": model_name,
                    "n_tests": len(model_result.tests),
                    "passed": model_result.passed_count,
                    "mean_pass_rate": confidence_interval.mean,
                    "ci_lower": confidence_interval.lower,
                    "ci_upper": confidence_interval.upper,
                    "std_dev": confidence_interval.std,
                    "cv": confidence_interval.cv,
                    "unstable": confidence_interval.cv > 0.5,
                }
            )

        return table_data
