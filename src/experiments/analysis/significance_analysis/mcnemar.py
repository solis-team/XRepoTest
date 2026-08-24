import logging
from itertools import combinations

import numpy as np
from scipy.stats import chi2  # type: ignore[import-untyped]
from statsmodels.stats.contingency_tables import mcnemar  # type: ignore[import-untyped]

from experiments.analysis.significance_analysis.data_collector import ModelResults
from experiments.analysis.significance_analysis.stats_utils import McNemarResult, align_test_results

logger = logging.getLogger(__name__)


class McNemarAnalyzer:
    def __init__(self, alpha: float = 0.05, correction: str = "bonferroni"):
        self.alpha = alpha
        self.correction = correction

    def compute_contingency_table(self, results_a: np.ndarray, results_b: np.ndarray) -> tuple[int, int, int, int]:
        both_pass = int(np.sum(results_a & results_b))
        both_fail = int(np.sum(~results_a & ~results_b))
        a_only = int(np.sum(results_a & ~results_b))
        b_only = int(np.sum(~results_a & results_b))
        return both_pass, a_only, b_only, both_fail

    def mcnemar_test(
        self,
        results_a: np.ndarray,
        results_b: np.ndarray,
        model_a_name: str,
        model_b_name: str,
        corrected_alpha: float | None = None,
    ) -> McNemarResult:
        if len(results_a) != len(results_b):
            raise ValueError("Result arrays must have the same length")

        if len(results_a) == 0:
            return McNemarResult(
                model_a=model_a_name,
                model_b=model_b_name,
                n_tests=0,
                a_only=0,
                b_only=0,
                both_pass=0,
                both_fail=0,
                chi_square=0.0,
                p_value=1.0,
                significant=False,
            )

        both_pass, a_only, b_only, both_fail = self.compute_contingency_table(results_a, results_b)
        table = np.array([[both_pass, a_only], [b_only, both_fail]])

        try:
            result = mcnemar(table, exact=False, correction=True)
            chi_square = float(result.statistic)
            p_value = float(result.pvalue)
        except Exception as error:
            logger.warning("statsmodels failed, using manual McNemar calculation: %s", error)
            if a_only + b_only == 0:
                chi_square = 0.0
                p_value = 1.0
            else:
                chi_square = float((abs(a_only - b_only) - 1) ** 2 / (a_only + b_only))
                p_value = float(1 - chi2.cdf(chi_square, df=1))

        alpha_threshold = corrected_alpha if corrected_alpha is not None else self.alpha
        return McNemarResult(
            model_a=model_a_name,
            model_b=model_b_name,
            n_tests=len(results_a),
            a_only=a_only,
            b_only=b_only,
            both_pass=both_pass,
            both_fail=both_fail,
            chi_square=chi_square,
            p_value=p_value,
            significant=p_value < alpha_threshold,
        )

    def compare_top_models(self, models_data: dict[str, ModelResults], top_n: int = 3) -> list[McNemarResult]:
        ranked_models = sorted(models_data.items(), key=lambda item: item[1].pass_rate, reverse=True)[:top_n]
        if len(ranked_models) < 2:
            logger.warning("Less than 2 models available for comparison")
            return []

        model_pairs = list(combinations(ranked_models, 2))
        corrected_alpha = self.alpha
        if self.correction == "bonferroni":
            corrected_alpha = self.alpha / len(model_pairs)

        results: list[McNemarResult] = []
        for (name_a, model_a), (name_b, model_b) in model_pairs:
            results_a, results_b = align_test_results(model_a.tests, model_b.tests)
            if len(results_a) == 0:
                continue

            result = self.mcnemar_test(
                results_a=results_a,
                results_b=results_b,
                model_a_name=name_a,
                model_b_name=name_b,
                corrected_alpha=corrected_alpha,
            )
            results.append(result)
            logger.info("%s", result)

        return results

    def compare_cross_mode(
        self,
        mode_a_data: dict[str, ModelResults],
        mode_b_data: dict[str, ModelResults],
        mode_a_name: str,
        mode_b_name: str,
    ) -> list[McNemarResult]:
        common_models = sorted(set(mode_a_data) & set(mode_b_data))
        if not common_models:
            return []

        results: list[McNemarResult] = []
        for model_name in common_models:
            results_a, results_b = align_test_results(
                mode_a_data[model_name].tests,
                mode_b_data[model_name].tests,
            )
            if len(results_a) == 0:
                continue

            results.append(
                self.mcnemar_test(
                    results_a=results_a,
                    results_b=results_b,
                    model_a_name=f"{model_name}@{mode_a_name}",
                    model_b_name=f"{model_name}@{mode_b_name}",
                )
            )

        return results
