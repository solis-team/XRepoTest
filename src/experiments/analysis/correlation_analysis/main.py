"""
Correlation Analysis Main Script

Loads evaluation results and computes correlations between Tessera metrics
and SWE-bench scores.
"""

from pathlib import Path
import json
import pandas as pd
import numpy as np
from collections import defaultdict

# Base path for evaluation data
BASE_PATH = Path(__file__).parent.parent.parent.parent / "experiments" / "evaluation" / "data" / "results"

# Languages to process
LANGUAGES = ['go', 'rust', 'julia', 'ruby', 'php']

# SWE-bench Verified scores (provider-reported, cross-verified via model pages/blogs)
# Sources: Anthropic blog, HuggingFace model cards, Qwen3-Coder-Next tech report (arXiv:2603.00729)
# Mapping: directory_name -> (display_name, swe_bench_score)
SWE_BENCH_MAPPING = {
    'claude-sonnet-4-5': ('Claude 4.5 Sonnet', 77.20),
    'accounts_fireworks_models_deepseek-v4-pro': ('DeepSeek V4', 80.60),
    'gpt-5.2': ('GPT-5.2', 75.80),
    'accounts_fireworks_models_minimax-m2p7': ('MiniMax-M2.7', 73.80),
    'accounts_fireworks_models_glm-5': ('GLM-5', 71.40),
    'qwen3-coder-next': ('Qwen3 Coder Next', 70.60),
    'accounts_fireworks_models_deepseek-v3p2': ('DeepSeek V3.2', 70.20),
    'accounts_fireworks_models_kimi-k2p5': ('Kimi K2.5', 76.80),
    'claude-haiku-4.5': ('Claude Haiku 4.5', 73.30),
    'accounts_fireworks_models_llama-v3p3-70b-instruct': ('Llama 3.3 70B', 22.00),
    '01-ai_Yi-Coder-9B-Chat': ('Yi-Coder 9B', 23.40),
    'accounts_fireworks_models_gpt-oss-120b': ('GPT-OSS-120B', 33.60),
    'accounts_fireworks_models_qwen3-8b': ('Qwen3 8B', None),  # no SWE-bench data
    'mistralai_Codestral-22B-v0.1': ('Codestral 22B', None),  # no SWE-bench data
}

METRIC_COLS = ['CSR', 'TPR', 'Cov', 'IR']
CORRELATION_METHODS = ['pearson', 'spearman', 'kendall']


def load_all_results(base_path: Path = None) -> dict:
    """Load all summary.json files for all models across languages."""
    if base_path is None:
        base_path = BASE_PATH

    all_results = defaultdict(dict)

    for lang in LANGUAGES:
        lang_path = base_path / lang / 'standard'

        if not lang_path.exists():
            print(f"Warning: {lang_path} does not exist")
            continue

        for model_dir in lang_path.iterdir():
            if not model_dir.is_dir():
                continue

            summary_file = model_dir / 'summary.json'
            if not summary_file.exists():
                continue

            with open(summary_file, 'r') as f:
                data = json.load(f)

            model_name = model_dir.name
            all_results[model_name][lang] = {
                'CSR': data.get('compiled_rate', 0),
                'TPR': data.get('test_pass_rate', 0),
                'Cov': data.get('line_coverage', 0),
                'IR': data.get('invocation_rate', 0),
                'total_samples': data.get('total_samples', 0)
            }

    return dict(all_results)


def aggregate_metrics(all_results: dict) -> pd.DataFrame:
    """Aggregate metrics per model (average across languages)."""
    aggregated_data = []

    for model_name, lang_data in all_results.items():
        csr_values = [lang_data[lang]['CSR'] for lang in lang_data]
        tpr_values = [lang_data[lang]['TPR'] for lang in lang_data]
        cov_values = [lang_data[lang]['Cov'] for lang in lang_data]
        ir_values = [lang_data[lang]['IR'] for lang in lang_data]

        aggregated_data.append({
            'Model': model_name,
            'CSR': np.mean(csr_values),
            'TPR': np.mean(tpr_values),
            'Cov': np.mean(cov_values),
            'IR': np.mean(ir_values),
            'num_languages': len(lang_data)
        })

    df = pd.DataFrame(aggregated_data)
    df = df.sort_values('CSR', ascending=False).reset_index(drop=True)
    return df


def compute_correlation_matrix(df: pd.DataFrame, metric_cols: list = None) -> pd.DataFrame:
    """Compute correlation matrix for metrics."""
    if metric_cols is None:
        metric_cols = METRIC_COLS
    return df[metric_cols].corr(method='pearson')


def filter_swe_bench_models(df: pd.DataFrame, mapping: dict = None) -> pd.DataFrame:
    """Filter to models with SWE-bench scores and add display names."""
    if mapping is None:
        mapping = SWE_BENCH_MAPPING

    df_swe = df[df['Model'].isin(mapping.keys())].copy()
    df_swe['Display_Name'] = df_swe['Model'].map(lambda x: mapping[x][0])
    df_swe['SWE-bench'] = df_swe['Model'].map(lambda x: mapping[x][1])
    # Filter out models without SWE-bench scores
    df_swe = df_swe[df_swe['SWE-bench'].notna()].copy()
    df_swe = df_swe.sort_values('SWE-bench', ascending=False).reset_index(drop=True)
    return df_swe


def compute_metric_correlations(df: pd.DataFrame, metrics: list = None) -> pd.DataFrame:
    """Compute correlations between SWE-bench and each Tessera metric."""
    if metrics is None:
        metrics = METRIC_COLS

    correlation_data = []
    for metric in metrics:
        row = {'Metric': metric}
        for method in CORRELATION_METHODS:
            corr_value = df['SWE-bench'].corr(df[metric], method=method)
            row[method.capitalize()] = corr_value
        correlation_data.append(row)

    return pd.DataFrame(correlation_data)


def main():
    """Run full correlation analysis pipeline."""
    print("=" * 60)
    print("Correlation Analysis: Tessera Metrics vs SWE-bench")
    print("=" * 60)

    # Load data
    print("\n1. Loading evaluation results...")
    all_results = load_all_results()
    print(f"   Loaded data for {len(all_results)} models across {len(LANGUAGES)} languages")

    # Aggregate metrics
    print("\n2. Aggregating metrics per model...")
    df_all_models = aggregate_metrics(all_results)
    print(f"   Aggregated data for {len(df_all_models)} models")

    # Full correlation matrix
    print("\n3. Computing correlation matrix (all models)...")
    corr_matrix = compute_correlation_matrix(df_all_models)
    print(corr_matrix.round(3))

    # Filter to SWE-bench models
    print("\n4. Filtering to models with SWE-bench scores...")
    df_swe = filter_swe_bench_models(df_all_models)
    print(f"   Filtered to {len(df_swe)} models")

    # Correlation with SWE-bench
    print("\n5. Computing correlations with SWE-bench...")
    df_correlations = compute_metric_correlations(df_swe)
    print("\n   Correlation Table: SWE-bench vs Tessera Metrics")
    print("   " + "-" * 55)
    print(f"   {'Metric':<10} {'Pearson':>12} {'Spearman':>12} {'Kendall':>12}")
    print("   " + "-" * 55)
    for _, row in df_correlations.iterrows():
        print(f"   {row['Metric']:<10} {row['Pearson']:>12.3f} {row['Spearman']:>12.3f} {row['Kendall']:>12.3f}")
    print("   " + "-" * 55)

    # Save results
    output_dir = Path(__file__).parent
    df_all_models.to_csv(output_dir / "all_models_metrics.csv", index=False, float_format='%.3f')
    df_swe.to_csv(output_dir / "swe_bench_models.csv", index=False, float_format='%.3f')
    df_correlations.to_csv(output_dir / "swe_bench_correlations.csv", index=False, float_format='%.3f')
    corr_matrix.to_csv(output_dir / "correlation_matrix.csv", float_format='%.3f')

    print(f"\n6. Results saved to {output_dir}/")
    print("   - all_models_metrics.csv")
    print("   - swe_bench_models.csv")
    print("   - swe_bench_correlations.csv")
    print("   - correlation_matrix.csv")

    return df_all_models, df_swe, df_correlations, corr_matrix


if __name__ == "__main__":
    main()