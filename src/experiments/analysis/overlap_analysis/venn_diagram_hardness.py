"""
Venn Diagram Visualization for Benchmark Hardness Analysis

This script visualizes which benchmark problems each model successfully solves
across all languages in file_context mode. The goal is to answer:
"Do different models solve the same set of problems, or do they have unique strengths?"

Models analyzed:
- Claude Sonnet 4.5 (claude-sonnet-4-5)
- GPT OSS 120B (accounts_fireworks_models_gpt-oss-120b)
- GPT-5.2 (gpt-5.2)

A sample is considered successfully solved if:
- checks[i]["tests"] == True (test passed)
- coverage_stats[i]["covered_lines"] > 0 (> 1 for Ruby)
"""

import json
from pathlib import Path
from typing import Dict, Set, Tuple, List
import matplotlib.pyplot as plt
from matplotlib_venn import venn3
import pandas as pd

from xrepotest.paths import get_evaluation_data_dir, get_project_root

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = get_project_root()

# Configuration
PROCESSED_ROOT = get_evaluation_data_dir() / "results"
LANGUAGES = ["go", "julia", "rust", "php", "ruby"]
MODE = "standard"

MODELS = {
    "Claude Sonnet 4.5": "claude-sonnet-4-5",
    "GPT-5.2": "gpt-5.2",
    "GPT OSS 120B": "accounts_fireworks_models_gpt-oss-120b"
}

# Sample identifier: (language, function_name, file_path)
SampleID = Tuple[str, str, str]


def load_detailed_results(lang: str, model_id: str) -> List[dict]:
    """Load detailed_results.jsonl for a specific language and model."""
    # Try detailed_results.jsonl first, then fall back to processed.jsonl
    path = PROCESSED_ROOT / lang / MODE / model_id / "detailed_results.jsonl"

    if not path.exists():
        path = PROCESSED_ROOT / lang / MODE / model_id / "processed.jsonl"

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
    
    print(f"Loaded {len(samples)} samples from {lang}/{model_id}")
    return samples


def is_sample_successful(sample: dict, lang: str) -> bool:
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
        
        # Handle None values or non-dict types
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


def get_sample_id(sample: dict, lang: str) -> SampleID:
    """Extract unique identifier for a sample."""
    function_name = sample.get("function_name", "")
    file_path = sample.get("file_path", "")
    return (lang, function_name, file_path)


def collect_successful_samples(lang: str, model_id: str) -> Set[SampleID]:
    """Collect all successfully solved samples for a model in a language."""
    samples = load_detailed_results(lang, model_id)
    successful = set()
    
    for sample in samples:
        if is_sample_successful(sample, lang):
            sample_id = get_sample_id(sample, lang)
            successful.add(sample_id)
    
    return successful


def build_model_success_sets() -> Dict[str, Set[SampleID]]:
    """Build success sets for all three models across all languages."""
    model_sets = {model_name: set() for model_name in MODELS.keys()}
    
    print("\n" + "="*70)
    print("Building success sets for each model...")
    print("="*70)
    
    for model_name, model_id in MODELS.items():
        print(f"\n{model_name} ({model_id}):")
        print("-" * 70)
        
        for lang in LANGUAGES:
            successful = collect_successful_samples(lang, model_id)
            model_sets[model_name].update(successful)
            print(f"  {lang:8s}: {len(successful):4d} successful samples")
        
        print(f"  {'TOTAL':8s}: {len(model_sets[model_name]):4d} successful samples")
    
    return model_sets


def calculate_venn_statistics(sets: Dict[str, Set[SampleID]]) -> dict:
    """Calculate overlap statistics for the three sets."""
    model_names = list(sets.keys())
    A, B, C = [sets[name] for name in model_names]
    
    # Calculate all regions
    only_A = A - B - C
    only_B = B - A - C
    only_C = C - A - B
    A_and_B_only = (A & B) - C
    A_and_C_only = (A & C) - B
    B_and_C_only = (B & C) - A
    all_three = A & B & C
    
    stats = {
        'model_names': model_names,
        'total_A': len(A),
        'total_B': len(B),
        'total_C': len(C),
        'only_A': len(only_A),
        'only_B': len(only_B),
        'only_C': len(only_C),
        'A_and_B_only': len(A_and_B_only),
        'A_and_C_only': len(A_and_C_only),
        'B_and_C_only': len(B_and_C_only),
        'all_three': len(all_three),
        'union': len(A | B | C)
    }
    
    return stats


def print_statistics(stats: dict):
    """Print detailed statistics about the overlap."""
    A_name, B_name, C_name = stats['model_names']
    
    print("\n" + "="*70)
    print("VENN DIAGRAM STATISTICS")
    print("="*70)
    
    print("\nTotal Successful Samples per Model:")
    print(f"  {A_name:25s}: {stats['total_A']:4d}")
    print(f"  {B_name:25s}: {stats['total_B']:4d}")
    print(f"  {C_name:25s}: {stats['total_C']:4d}")
    print(f"  {'Union (at least one)':25s}: {stats['union']:4d}")
    
    # Handle edge case where no samples were found
    if stats['union'] == 0:
        print("\n⚠️  WARNING: No successful samples found for any model!")
        print("Please check that:")
        print("  1. detailed_results.jsonl files exist in the expected locations")
        print("  2. The file_context mode has been evaluated for these models")
        print(f"  3. Looking in: {PROCESSED_ROOT}")
        return
    
    print("\nExclusive Regions (solved by only one model):")
    print(f"  Only {A_name:20s}: {stats['only_A']:4d} ({100*stats['only_A']/stats['union']:.1f}%)")
    print(f"  Only {B_name:20s}: {stats['only_B']:4d} ({100*stats['only_B']/stats['union']:.1f}%)")
    print(f"  Only {C_name:20s}: {stats['only_C']:4d} ({100*stats['only_C']/stats['union']:.1f}%)")
    
    print("\nPairwise Intersections (solved by exactly two models):")
    print(f"  {A_name} ∩ {B_name} (not {C_name}): {stats['A_and_B_only']:4d} ({100*stats['A_and_B_only']/stats['union']:.1f}%)")
    print(f"  {A_name} ∩ {C_name} (not {B_name}): {stats['A_and_C_only']:4d} ({100*stats['A_and_C_only']/stats['union']:.1f}%)")
    print(f"  {B_name} ∩ {C_name} (not {A_name}): {stats['B_and_C_only']:4d} ({100*stats['B_and_C_only']/stats['union']:.1f}%)")
    
    print("\nTriple Intersection (solved by all three models):")
    print(f"  All three models: {stats['all_three']:4d} ({100*stats['all_three']/stats['union']:.1f}%)")
    
    # Calculate coverage percentages
    print("\nOverlap Coverage (what % of each model's solutions are shared):")
    if stats['total_A'] > 0:
        shared_A = stats['total_A'] - stats['only_A']
        print(f"  {A_name}: {100*shared_A/stats['total_A']:.1f}% shared with at least one other")
    if stats['total_B'] > 0:
        shared_B = stats['total_B'] - stats['only_B']
        print(f"  {B_name}: {100*shared_B/stats['total_B']:.1f}% shared with at least one other")
    if stats['total_C'] > 0:
        shared_C = stats['total_C'] - stats['only_C']
        print(f"  {C_name}: {100*shared_C/stats['total_C']:.1f}% shared with at least one other")


def create_venn_diagram(sets: Dict[str, Set[SampleID]], output_path: str = "venn_diagram_hardness.pdf"):
    """Create and save a 3-way Venn diagram."""
    model_names = list(sets.keys())
    A, B, C = [sets[name] for name in model_names]
    
    # Create figure with larger size
    fig, ax = plt.subplots(figsize=(12, 10))
    
    # Create Venn diagram
    venn = venn3([A, B, C], set_labels=model_names, ax=ax, alpha=0.6,
                 set_colors=('#ff9999', '#66b3ff', '#99ff99'))
    
    # Enhance label styling
    for text in venn.set_labels:
        if text:
            text.set_fontsize(14)
            text.set_fontweight('bold')
    
    # Enhance subset label styling
    for text in venn.subset_labels:
        if text:
            text.set_fontsize(12)
    
    plt.tight_layout()
    
    # Save figure
    output_file = Path(output_path)
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"\n✓ Venn diagram saved to: {output_file.absolute()}")
    
    plt.show()


def analyze_language_breakdown(sets: Dict[str, Set[SampleID]]):
    """Analyze success rates broken down by language."""
    print("\n" + "="*70)
    print("LANGUAGE-WISE BREAKDOWN")
    print("="*70)
    
    # Create a table
    data = []
    
    for lang in LANGUAGES:
        row = {'Language': lang}
        
        for model_name, model_id in MODELS.items():
            successful = collect_successful_samples(lang, model_id)
            row[model_name] = len(successful)
        
        data.append(row)
    
    df = pd.DataFrame(data)
    print("\n" + df.to_string(index=False))
    
    # Save to CSV
    output_path = SCRIPT_DIR / "language_breakdown.csv"
    df.to_csv(output_path, index=False)
    print(f"\n✓ Language breakdown saved to: {output_path.absolute()}")


def main():
    """Main execution function."""
    print("="*70)
    print("BENCHMARK HARDNESS ANALYSIS - VENN DIAGRAM")
    print("="*70)
    print(f"\nProject Root: {PROJECT_ROOT}")
    print(f"Data Path: {PROCESSED_ROOT}")
    print(f"Mode: {MODE}")
    print(f"Languages: {', '.join(LANGUAGES)}")
    print(f"Models: {len(MODELS)}")
    for name, model_id in MODELS.items():
        print(f"  - {name} ({model_id})")
    
    # Build success sets
    model_sets = build_model_success_sets()
    
    # Calculate and print statistics
    stats = calculate_venn_statistics(model_sets)
    print_statistics(stats)
    
    # Only create visualizations if we have data
    if stats['union'] > 0:
        # Create Venn diagram
        output_path = SCRIPT_DIR / "venn_diagram_hardness.pdf"
        create_venn_diagram(model_sets, str(output_path))
        
        # Language breakdown analysis
        analyze_language_breakdown(model_sets)
        
        print("\n" + "="*70)
        print("ANALYSIS COMPLETE")
        print("="*70)
    else:
        print("\n" + "="*70)
        print("ANALYSIS ABORTED - No data found")
        print("="*70)


if __name__ == "__main__":
    main()
