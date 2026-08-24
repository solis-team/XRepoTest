"""
Combined Spider/Radar Chart Visualization - Two Charts Side by Side

This script creates a single figure with two spider charts side by side:
- Left: Standard mode (14 models)
- Right: File context mode (3 models)

Domains are merged across all languages.
"""

import json
from pathlib import Path
from typing import Dict, List
import matplotlib.pyplot as plt
import numpy as np
from collections import defaultdict
import matplotlib.lines as mlines

from xrepotest.paths import get_evaluation_data_dir

SCRIPT_DIR = Path(__file__).parent.resolve()

# Configuration
PROCESSED_ROOT = get_evaluation_data_dir() / "results"

# All available models for standard mode
STANDARD_MODELS = [
    "accounts_fireworks_models_deepseek-v3p2",
    "accounts_fireworks_models_deepseek-v4-pro",
    "accounts_fireworks_models_glm-5",
    "accounts_fireworks_models_gpt-oss-120b",
    "accounts_fireworks_models_kimi-k2p5",
    "accounts_fireworks_models_llama-v3p3-70b-instruct",
    "accounts_fireworks_models_minimax-m2p7",
    "accounts_fireworks_models_qwen3-8b",
    "claude-haiku-4.5",
    "claude-sonnet-4-5",
    "mistralai_Codestral-22B-v0.1",
    "gpt-5.2",
    "qwen3-coder-next",
    "01-ai_Yi-Coder-9B-Chat",
]

STANDARD_DISPLAY_NAMES = {
    "accounts_fireworks_models_deepseek-v3p2": "DeepSeek V3.2",
    "accounts_fireworks_models_deepseek-v4-pro": "DeepSeek V4 Pro",
    "accounts_fireworks_models_glm-5": "GLM-5",
    "accounts_fireworks_models_gpt-oss-120b": "GPT-OSS 120B",
    "accounts_fireworks_models_kimi-k2p5": "Kimi K2 Pro",
    "accounts_fireworks_models_llama-v3p3-70b-instruct": "Llama 3.3 70B",
    "accounts_fireworks_models_minimax-m2p7": "Minimax 2.7",
    "accounts_fireworks_models_qwen3-8b": "Qwen3 8B",
    "claude-haiku-4.5": "Claude 4.5 Haiku",
    "claude-sonnet-4-5": "Claude 4.5 Sonnet",
    "mistralai_Codestral-22B-v0.1": "Codestral 22B",
    "gpt-5.2": "GPT-5.2",
    "qwen3-coder-next": "Qwen3 Coder Next",
    "01-ai_Yi-Coder-9B-Chat": "Yi-Coder 9B",
}

# File context mode models (only available for go language)
FILE_CONTEXT_MODELS = [
    "accounts_fireworks_models_gpt-oss-120b",
    "claude-sonnet-4-5",
    "gpt-5.2",
]

FILE_CONTEXT_DISPLAY_NAMES = {
    "accounts_fireworks_models_gpt-oss-120b": "GPT-OSS 120B",
    "claude-sonnet-4-5": "Claude 4.5 Sonnet",
    "gpt-5.2": "GPT-5.2",
}

# Repository to domain mapping
REPO_DOMAINS = {
    "Julia": {
        "Distributions.jl": "Scientific Computing",
        "DataStructures.jl": "Data Structure & Algorithm",
        "StatsBase.jl": "Scientific Computing",
        "QuantEcon.jl": "Scientific Computing",
        "Turing.jl": "Scientific Computing",
        "dataframes.jl": "Scientific Computing",
    },
    "rust": {
        "rust-master": "Data Structure & Algorithm",
        "alacritty": "Developer Tool",
        "burn": "Scientific Computing",
        "starship": "Developer Tool",
        "ripgrep": "Developer Tool",
        "hyper": "Web/Framework",
        "nom": "Developer Tool",
        "uuid": "Utilities",
    },
    "go": {
        "go-master": "Data Structure & Algorithm",
        "chi": "Web/Framework",
        "cli": "Developer Tool",
        "ollama": "Developer Tool",
        "cobra": "Developer Tool",
        "hugo": "Web/Framework",
        "client_golang": "Web/Framework",
        "zap": "Utilities",
    },
    "php": {
        "Faker": "Testing & Mocking",
        "mockery": "Testing & Mocking",
        "Carbon": "Utilities",
        "csv": "Utilities",
        "PHP-Parser": "Utilities",
        "PHPMailer": "Utilities",
        "flysystem": "Utilities",
        "monolog": "Utilities",
        "uuid": "Utilities",
    },
    "ruby": {
        "rspec-core": "Testing & Mocking",
        "capybara": "Testing & Mocking",
        "httparty": "Web/Framework",
        "pundit": "Web/Framework",
        "dotenv": "Utilities",
        "hashie": "Utilities",
        "grape": "Web/Framework",
        "hanami": "Web/Framework",
        "rom": "Utilities",
        "shoryuken": "Developer Tool",
    }
}

# All domains (merged across languages) - 6 domains per paper
ALL_DOMAINS = [
    "Scientific Computing",
    "Data Structure & Algorithm",
    "Developer Tool",
    "Web/Framework",
    "Testing & Mocking",
    "Utilities",
]

METRIC = "test_pass_rate"


# Mapping from actual folder names to short repo names (for domain lookup)
FOLDER_TO_REPO = {
    "Julia": {},
    "rust": {
        "rust-master": "rust-master",
        "burn-main": "burn",
        "alacritty-master": "alacritty",
        "starship-master": "starship",
        "ripgrep-master": "ripgrep",
    },
    "go": {
        "go-master": "go-master",
        "chi-master": "chi",
        "cli-main": "cli",
        "ollama-main": "ollama",
        "cobra-main": "cobra",
        "hugo-master": "hugo",
    },
    "php": {},
    "ruby": {},
}


def extract_repo_from_path(file_path: str, lang: str) -> str:
    """Extract repository name from file path."""
    parts = file_path.split('/')
    if len(parts) > 0:
        folder_name = parts[0]
        if lang in FOLDER_TO_REPO and folder_name in FOLDER_TO_REPO[lang]:
            return FOLDER_TO_REPO[lang][folder_name]
        return folder_name
    return "Unknown"


def get_domain_for_repo(repo: str, lang: str) -> str:
    """Get domain category for a repository."""
    if lang in REPO_DOMAINS and repo in REPO_DOMAINS[lang]:
        return REPO_DOMAINS[lang][repo]
    return "Unknown"


def load_detailed_results(lang: str, model_id: str, mode: str) -> List[dict]:
    """Load detailed_results.jsonl for a specific language and model."""
    path = PROCESSED_ROOT / lang / mode / model_id / "detailed_results.jsonl"

    if not path.exists():
        return []

    samples = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return samples


def calculate_success_rate(sample: dict, lang: str) -> bool:
    """Determine if a sample has at least one successful test."""
    checks = sample.get("checks", [])
    coverage_stats = sample.get("coverage_stats", [])

    if not checks or not coverage_stats:
        return False

    for i in range(len(checks)):
        check = checks[i]
        coverage = coverage_stats[i]

        if not isinstance(check, dict):
            check = {}
        if not isinstance(coverage, dict):
            coverage = {}

        test_passed = check.get("tests", False)
        covered_lines = coverage.get("covered_lines", 0)
        coverage_threshold = 1 if lang == "ruby" else 0

        if test_passed and covered_lines > coverage_threshold:
            return True

    return False


def compute_domain_metrics_merged(model_id: str, mode: str) -> Dict[str, float]:
    """Compute metrics for each domain across all languages."""
    all_languages = list(REPO_DOMAINS.keys())
    domain_samples = defaultdict(list)

    for lang in all_languages:
        samples = load_detailed_results(lang, model_id, mode)

        for sample in samples:
            file_path = sample.get("file_path", "")
            repo = extract_repo_from_path(file_path, lang)
            domain = get_domain_for_repo(repo, lang)

            if domain != "Unknown":
                domain_samples[domain].append((sample, lang))

    domain_metrics = {}
    for domain, domain_sample_list in domain_samples.items():
        if not domain_sample_list:
            domain_metrics[domain] = 0.0
            continue

        successful_count = sum(1 for s, lang in domain_sample_list if calculate_success_rate(s, lang))
        total_count = len(domain_sample_list)
        domain_metrics[domain] = (successful_count / total_count * 100) if total_count > 0 else 0.0

    return domain_metrics


def create_combined_spider_chart(output_dir: Path):
    """Create a single figure with two spider charts side by side (merged domains)."""

    if not ALL_DOMAINS:
        print("No domains found")
        return

    axis_labels = ALL_DOMAINS

    # Create figure with two subplots
    fig = plt.figure(figsize=(24, 12))

    # Colors and styles for 14 standard models
    standard_colors = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
        '#3aadd9', '#f5c243', '#45a54a', '#d94436'
    ]
    standard_linestyles = ['-', '--', '-.', ':', '-', '--', '-.', ':', '-', '--', '-.', ':', '-', '--']
    standard_markers = ['o', 's', '^', 'D', 'v', 'p', '*', 'h', 'H', '+', 'X', 'd', 'x', 'P']

    # Colors and styles for 3 file context models
    file_context_colors = ['#1f77b4', '#ff7f0e', '#2ca02c']
    # file_context models: gpt-oss-120b (idx 3), claude-sonnet-4-5 (idx 6), gpt-5.2 (idx 10)
    # Use same line styles as standard mode for visual matching
    file_context_linestyles = ['-', '-.', '--']  # matches: gpt-oss='-', claude-sonnet='-.', gpt-5.2='--'
    file_context_markers = ['o', 's', '^']

    # Setup angles for 6 domains
    num_vars = len(ALL_DOMAINS)
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    angles += angles[:1]

    # ============ LEFT SUBPLOT: STANDARD MODE ============
    ax1 = fig.add_subplot(121, projection='polar')

    # Collect data for standard mode
    for idx, model_id in enumerate(STANDARD_MODELS):
        domain_metrics = compute_domain_metrics_merged(model_id, "standard")
        values = [domain_metrics.get(domain, 0.0) for domain in ALL_DOMAINS]
        values_closed = values + values[:1]

        model_name = STANDARD_DISPLAY_NAMES.get(model_id, model_id)
        ax1.plot(angles, values_closed, linewidth=2.0, linestyle=standard_linestyles[idx],
                color=standard_colors[idx], marker=standard_markers[idx],
                markersize=7, alpha=0.85)
        ax1.fill(angles, values_closed, alpha=0.08, color=standard_colors[idx])

    ax1.set_xticks(angles[:-1])
    ax1.set_xticklabels(axis_labels, size=12)
    ax1.set_ylim(0, 50)
    ax1.set_yticks([0, 10, 20, 30, 40, 50])
    ax1.set_yticklabels(['0', '10', '20', '30', '40', '50'], size=11)
    ax1.grid(True, linestyle='--', linewidth=0.5, alpha=0.7)
    ax1.set_title('(1) Standard Mode', size=20, fontweight='bold', pad=15)

    # ============ RIGHT SUBPLOT: FILE CONTEXT MODE ============
    ax2 = fig.add_subplot(122, projection='polar')

    # Collect data for file context mode
    # Map FILE_CONTEXT models to their STANDARD indices for matching visual style
    file_context_to_standard_idx = {
        0: 3,   # gpt-oss-120b → STANDARD[3]
        1: 9,   # claude-sonnet-4-5 → STANDARD[9]
        2: 11,  # gpt-5.2 → STANDARD[11]
    }

    for idx, model_id in enumerate(FILE_CONTEXT_MODELS):
        std_idx = file_context_to_standard_idx[idx]
        domain_metrics = compute_domain_metrics_merged(model_id, "file_context")
        values = [domain_metrics.get(domain, 0.0) for domain in ALL_DOMAINS]
        values_closed = values + values[:1]

        model_name = FILE_CONTEXT_DISPLAY_NAMES.get(model_id, model_id)
        # Use SAME color, line style, and marker as the corresponding standard model
        ax2.plot(angles, values_closed, linewidth=2.5,
                color=standard_colors[std_idx],
                linestyle=standard_linestyles[std_idx],
                marker=standard_markers[std_idx],
                markersize=10, alpha=0.9)
        ax2.fill(angles, values_closed, alpha=0.15, color=standard_colors[std_idx])

    ax2.set_xticks(angles[:-1])
    ax2.set_xticklabels(axis_labels, size=12)
    ax2.set_ylim(0, 60)
    ax2.set_yticks([0, 10, 20, 30, 40, 50, 60])
    ax2.set_yticklabels(['0', '10', '20', '30', '40', '50', '60'], size=11)
    ax2.grid(True, linestyle='--', linewidth=0.5, alpha=0.7)
    ax2.set_title('(2) File Context Mode', size=20, fontweight='bold', pad=15)

    # Create combined legend with 14 unique models (the 3 file_context models use same color/style as standard)
    legend_handles = []

    # All 14 standard mode models (file_context uses same colors/styles for its 3 models)
    for idx, model_id in enumerate(STANDARD_MODELS):
        model_name = STANDARD_DISPLAY_NAMES.get(model_id, model_id)
        handle = mlines.Line2D([], [], color=standard_colors[idx],
                              linestyle=standard_linestyles[idx],
                              marker=standard_markers[idx], markersize=8,
                              label=f"{model_name}", linewidth=2)
        legend_handles.append(handle)

    # Add legend to the top of the figure
    fig.legend(legend_handles, [h.get_label() for h in legend_handles],
              loc='upper center', bbox_to_anchor=(0.5, 1.02),
              fontsize=11, framealpha=0.95, ncol=7,
              title='Standard Mode — File Context models share colors/styles with their Standard counterparts', title_fontsize=11)

    plt.tight_layout(rect=[0, 0, 1, 0.95], pad=3.0)

    # Save figure
    output_file = output_dir / "spider_combined_merged.pdf"
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✓ Saved: {output_file}")

    output_file_png = output_dir / "spider_combined_merged.png"
    plt.savefig(output_file_png, dpi=300, bbox_inches='tight')
    print(f"✓ Saved: {output_file_png}")

    plt.close()


def main():
    """Main execution function."""
    output_dir = SCRIPT_DIR / "spider_charts"
    output_dir.mkdir(exist_ok=True)

    print("="*70)
    print("COMBINED SPIDER CHART GENERATION (MERGED DOMAINS)")
    print("="*70)
    print(f"Left: Standard mode ({len(STANDARD_MODELS)} models)")
    print(f"Right: File context mode ({len(FILE_CONTEXT_MODELS)} models)")
    print(f"Domains: {', '.join(ALL_DOMAINS)}")
    print(f"Output Directory: {output_dir}")
    print()

    try:
        create_combined_spider_chart(output_dir)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*70)
    print("GENERATION COMPLETE")
    print("="*70)


if __name__ == "__main__":
    main()