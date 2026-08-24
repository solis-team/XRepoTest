from pathlib import Path
import logging

from experiments.analysis.significance_analysis.stats_utils import McNemarResult

logger = logging.getLogger(__name__)


class RebuttalGenerator:
    def generate_rebuttal_paragraph(
        self,
        all_bootstrap_results: dict[str, dict[str, list[dict[str, object]]]],
        all_mcnemar_results: dict[str, dict[str, list[McNemarResult]]],
        n_bootstrap_iterations: int = 10000,
    ) -> str:
        total_settings = sum(len(modes) for modes in all_bootstrap_results.values())
        total_comparisons = sum(
            len(results)
            for mode_data in all_mcnemar_results.values()
            for results in mode_data.values()
        )
        significant_comparisons = sum(
            sum(result.significant for result in results)
            for mode_data in all_mcnemar_results.values()
            for results in mode_data.values()
        )
        non_overlapping_count = 0
        model_wins: dict[str, int] = {}
        model_significant_wins: dict[str, int] = {}

        for language, mode_data in all_bootstrap_results.items():
            for mode, rows in mode_data.items():
                if not rows:
                    continue

                top_model = str(rows[0]["model"])
                model_wins[top_model] = model_wins.get(top_model, 0) + 1

                if len(rows) >= 2 and self._to_float(rows[0].get("ci_lower")) > self._to_float(rows[1].get("ci_upper")):
                    non_overlapping_count += 1

                for result in all_mcnemar_results.get(language, {}).get(mode, []):
                    if result.model_a == top_model and result.significant:
                        model_significant_wins[top_model] = model_significant_wins.get(top_model, 0) + 1

        most_robust_model = max(model_wins.items(), key=lambda item: item[1])[0] if model_wins else "N/A"
        wins = model_wins.get(most_robust_model, 0)
        significant_wins = model_significant_wins.get(most_robust_model, 0)
        significant_ratio = f"{significant_comparisons}/{total_comparisons}" if total_comparisons else "0/0"
        ci_separation_ratio = f"{non_overlapping_count}/{total_settings}" if total_settings else "N/A"
        wins_ratio = f"{wins}/{total_settings}" if total_settings else "N/A"

        return (
            f"We ran bootstrap resampling ({n_bootstrap_iterations:,} iterations) and McNemar tests across "
            f"{total_settings} language/mode settings to validate ranking stability under low pass rates. "
            f"Confidence intervals for the top model do not overlap with the runner-up in "
            f"{ci_separation_ratio} settings, and {significant_ratio} top-model pairwise "
            f"comparisons are statistically significant after correction. "
            f"The most consistent winner is **{most_robust_model}** ({wins_ratio} top ranks, "
            f"{significant_wins} significant wins)."
        )

    @staticmethod
    def _to_float(value: object) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        return 0.0

    def save_rebuttal(self, rebuttal_text: str, output_path: Path) -> None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            handle.write(rebuttal_text)
        logger.info("Saved rebuttal text to %s", output_path)
