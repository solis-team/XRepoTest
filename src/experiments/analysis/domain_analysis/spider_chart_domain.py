"""
Spider/Radar Chart Visualization for Domain-Based Performance Analysis

This script creates spider charts showing model performance across different domains
merged across all languages. Each axis represents a domain.
"""

import json
from pathlib import Path
from typing import Dict, List
import matplotlib.pyplot as plt
import numpy as np
from collections import defaultdict

from xrepotest.paths import get_evaluation_data_dir

SCRIPT_DIR = Path(__file__).parent.resolve()

# Configuration
PROCESSED_ROOT = get_evaluation_data_dir() / "results"

# All available models for standard mode
AVAILABLE_MODELS = [
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

MODEL_DISPLAY_NAMES = {
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

# All domains (merged across languages)
ALL_DOMAINS = [
    "Scientific Computing",
    "Data Structure & Algorithm",
    "Developer Tool",
    "Web/Framework",
    "Testing & Mocking",
    "Utilities",
]

# Evaluation mode
MODE = "standard"

# Metric to visualize (choose one)
METRIC = "test_pass_rate"  # Options: "compiled_rate", "test_pass_rate", "line_coverage", "invocation_rate"


# Mapping from actual folder names to short repo names (for domain lookup)
FOLDER_TO_REPO = {
    "Julia": {},
    "rust": {
        "rust-master": "rust-master",  # stays same
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

    if lang == "Julia":
        if len(parts) > 0:
            return parts[0]
    elif lang == "rust":
        if len(parts) > 0:
            folder_name = parts[0]
            return FOLDER_TO_REPO["rust"].get(folder_name, folder_name)
    elif lang == "go":
        if len(parts) > 0:
            folder_name = parts[0]
            return FOLDER_TO_REPO["go"].get(folder_name, folder_name)
    elif lang in ["php", "ruby"]:
        if len(parts) > 0:
            return parts[0]

    return "Unknown"


def get_domain_for_repo(repo: str, lang: str) -> str:
    """Get domain category for a repository."""
    if lang in REPO_DOMAINS and repo in REPO_DOMAINS[lang]:
        return REPO_DOMAINS[lang][repo]
    return "Unknown"


def load_detailed_results(lang: str, model_id: str) -> List[dict]:
    """Load detailed_results.jsonl for a specific language and model."""
    path = PROCESSED_ROOT / lang / MODE / model_id / "detailed_results.jsonl"
    
    if not path.exists():
        print(f"Warning: File not found: {path}")
        return []
    
    samples = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"Warning: Failed to parse line in {path}: {e}")
                    continue
    
    return samples


def calculate_success_rate(sample: dict, lang: str) -> bool:
    """
    Determine if a sample has at least one successful test.
    
    Success criteria:
    - checks[i]["tests"] == True (test passed)
    - coverage_stats[i]["covered_lines"] > 0 (or > 1 for Ruby)
    """
    checks = sample.get("checks", [])
    coverage_stats = sample.get("coverage_stats", [])
    
    if not checks or not coverage_stats:
        return False
    
    # Check each test
    for i in range(len(checks)):
        check = checks[i]
        coverage = coverage_stats[i]
        
        if not isinstance(check, dict):
            check = {}
        if not isinstance(coverage, dict):
            coverage = {}
        
        test_passed = check.get("tests", False)
        covered_lines = coverage.get("covered_lines", 0)
        
        # Ruby has stricter threshold
        coverage_threshold = 1 if lang == "ruby" else 0
        
        if test_passed and covered_lines > coverage_threshold:
            return True
    
    return False


def compute_domain_metrics(model_id: str) -> Dict[str, float]:
    """
    Compute the specified metric for each domain across all languages.

    Returns: Dict mapping domain name to metric value (percentage)
    """
    all_languages = list(REPO_DOMAINS.keys())
    domain_samples = defaultdict(list)

    for lang in all_languages:
        samples = load_detailed_results(lang, model_id)

        for sample in samples:
            file_path = sample.get("file_path", "")
            repo = extract_repo_from_path(file_path, lang)
            domain = get_domain_for_repo(repo, lang)

            if domain != "Unknown":
                domain_samples[domain].append((sample, lang))

    # Calculate metrics for each domain
    domain_metrics = {}

    for domain, domain_sample_list in domain_samples.items():
        if not domain_sample_list:
            domain_metrics[domain] = 0.0
            continue

        successful_count = sum(1 for s, lang in domain_sample_list if calculate_success_rate(s, lang))
        total_count = len(domain_sample_list)

        # Calculate percentage
        domain_metrics[domain] = (successful_count / total_count * 100) if total_count > 0 else 0.0

    return domain_metrics


def create_unified_spider_chart(output_dir: Path):
    """
    Create a single spider chart with domains as axes (merged across languages),
    showing all selected models.
    """
    if not ALL_DOMAINS:
        print("No domains found")
        return

    # Create axis labels from domains
    axis_labels = ALL_DOMAINS

    # Collect data for all models
    model_data = {}
    for model_id in AVAILABLE_MODELS:
        domain_metrics = compute_domain_metrics(model_id)
        values = [domain_metrics.get(domain, 0.0) for domain in ALL_DOMAINS]
        model_data[model_id] = values

    # Check if we have any data
    if not any(any(values) for values in model_data.values()):
        print("No data available for any model")
        return

    # Create spider chart
    num_vars = len(ALL_DOMAINS)
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()

    # Close the plot
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(14, 14), subplot_kw=dict(projection='polar'))

    # Colors and styles for 14 models
    colors = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
        '#3aadd9', '#f5c243', '#45a54a', '#d94436'
    ]
    linestyles = ['-', '--', '-.', ':', '-', '--', '-.', ':', '-', '--', '-.', ':', '-', '--']
    markers = ['o', 's', '^', 'D', 'v', 'p', '*', 'h', 'H', '+', 'X', 'd', 'x', 'P']

    for idx, model_id in enumerate(AVAILABLE_MODELS):
        values = model_data[model_id]
        # Close the plot
        values_closed = values + values[:1]

        # Get model display name
        model_name = MODEL_DISPLAY_NAMES.get(model_id, model_id)

        ax.plot(angles, values_closed, linewidth=2.0, linestyle=linestyles[idx % len(linestyles)],
                label=model_name, color=colors[idx % len(colors)],
                marker=markers[idx % len(markers)], markersize=8)
        ax.fill(angles, values_closed, alpha=0.1, color=colors[idx % len(colors)])

    # Set labels
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(axis_labels, size=14)

    # Set y-axis limits
    ax.set_ylim(0, 60)
    ax.set_yticks([0, 10, 20, 30, 40, 50, 60])
    ax.set_yticklabels(['0', '10', '20', '30', '40', '50', '60'], size=14)

    # Add grid
    ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.7)

    # Add legend
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=10)

    plt.tight_layout(pad=2.0)

    # Save figure
    output_file = output_dir / f"spider_merged_{MODE}.pdf"
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✓ Saved: {output_file}")

    # Also save as PNG
    output_file_png = output_dir / f"spider_merged_{MODE}.png"
    plt.savefig(output_file_png, dpi=300, bbox_inches='tight')
    print(f"✓ Saved: {output_file_png}")

    plt.close()


def create_all_spider_charts():
    """Create unified spider chart for all domains merged across languages."""
    output_dir = SCRIPT_DIR / "spider_charts"
    output_dir.mkdir(exist_ok=True)

    print("="*70)
    print("MERGED DOMAIN SPIDER CHART GENERATION")
    print("="*70)
    print(f"Metric: {METRIC}")
    print(f"Mode: {MODE}")
    print(f"Models: {', '.join([MODEL_DISPLAY_NAMES[m] for m in AVAILABLE_MODELS])}")
    print(f"Domains: {', '.join(ALL_DOMAINS)}")
    print(f"Output Directory: {output_dir}")
    print()
    
    try:
        create_unified_spider_chart(output_dir)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*70)
    print("GENERATION COMPLETE")
    print("="*70)
    print(f"Chart saved to: {output_dir.absolute()}")


def print_domain_statistics():
    """Print statistics about domains and repositories."""
    print("\n" + "="*70)
    print("DOMAIN STATISTICS")
    print("="*70)
    
    for lang, repos in REPO_DOMAINS.items():
        print(f"\n{lang}:")
        domain_count = defaultdict(int)
        for repo, domain in repos.items():
            domain_count[domain] += 1
            print(f"  {repo:30s} → {domain}")
        
        print("\n  Domain distribution:")
        for domain, count in sorted(domain_count.items()):
            print(f"    {domain:30s}: {count} repos")


def main():
    """Main execution function."""
    print_domain_statistics()
    create_all_spider_charts()


if __name__ == "__main__":
    main()
