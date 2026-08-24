"""
Evaluate LLM-generated tests from the generated_tests directory

This script loads test cases from JSONL files and evaluates them with coverage measurement.
Results are saved to evaluation_summary.json in each language/model directory.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from evaluators import evaluate_llm_test_generations


def load_tests_from_directory(input_dir: str = "generated_tests", 
                              model: Optional[str] = None) -> tuple[Dict[str, List], Dict[str, List[str]]]:
    """
    Load generated tests from JSONL files
    
    Args:
        input_dir: Directory containing generated tests (default: "generated_tests")
        model: Optional model name to filter by (e.g., "gpt-4", "glm-4.7")
        
    Returns:
        Tuple of (language_data, generated_responses)
        - language_data: Dict mapping language to list of task data
        - generated_responses: Dict mapping language to list of generated test strings
    """
    input_path = Path(input_dir)
    
    if not input_path.exists():
        raise ValueError(f"Input directory does not exist: {input_dir}")
    
    print(f"Loading tests from: {input_path}")
    print("=" * 60)
    
    language_data = {}
    generated_responses = {}
    
    for lang_dir in input_path.iterdir():
        if not lang_dir.is_dir():
            continue
        
        lang = lang_dir.name
        print(f"\nProcessing {lang}...")
        
        # Look for model subdirectories
        model_dirs = [d for d in lang_dir.iterdir() if d.is_dir()]
        
        if not model_dirs:
            print(f"  No model directories found in {lang_dir}")
            continue
        
        # Filter by model if specified
        if model:
            model_sanitized = model.replace('/', '_').replace(':', '_')
            model_dirs = [d for d in model_dirs if d.name == model_sanitized]
            if not model_dirs:
                print(f"  No directory found for model {model}")
                continue
        
        # Process each model directory
        for model_dir in model_dirs:
            model_name = model_dir.name
            jsonl_file = model_dir / "generated.jsonl"
            
            if not jsonl_file.exists():
                print(f"  Skipping {model_name}: no generated.jsonl found")
                continue
            
            print(f"  Loading {model_name}/generated.jsonl...")
            
            tasks = []
            tests = []
            
            # Load JSONL file
            with open(jsonl_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if line.strip():
                        try:
                            task_data = json.loads(line)
                            tasks.append(task_data)
                            
                            # Handle None values from failed generations
                            test_content = task_data.get('generated_test')
                            if test_content is None:
                                test_content = f"ERROR: Test generation failed for {task_data.get('task_id', 'unknown')}"
                            tests.append(test_content)
                            
                        except json.JSONDecodeError as e:
                            print(f"    Warning: Skipping line {line_num} - invalid JSON: {e}")
                            continue
            
            print(f"    Loaded {len(tasks)} tasks with {len(tests)} test cases")
            
            # Store by language (combining all models for now)
            # If you want to separate by model, use f"{lang}_{model_name}" as key
            if lang not in language_data:
                language_data[lang] = []
                generated_responses[lang] = []
            
            language_data[lang].extend(tasks)
            generated_responses[lang].extend(tests)
    
    print(f"\n{'=' * 60}")
    print(f"Loaded {sum(len(tasks) for tasks in language_data.values())} total tasks")
    print(f"Languages: {', '.join(language_data.keys())}")
    
    return language_data, generated_responses


def save_evaluation_results(results: Dict, output_file: str = "evaluation_results.json"):
    """Save evaluation results to JSON file"""
    output_path = Path(output_file)
    
    # Create summary without detailed_results (too large)
    summary = {
        'total_evaluated': results['total_evaluated'],
        'total_tests_passed': results['total_tests_passed'],
        'overall_pass_rate': results['total_tests_passed'] / results['total_evaluated'] * 100 if results['total_evaluated'] > 0 else 0,
        'test_pass_rates': results['test_pass_rates'],
        'coverage_stats': results['coverage_stats']
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n✓ Saved evaluation summary to {output_path}")
    
    # Optionally save detailed results to separate file
    detailed_file = output_path.parent / f"{output_path.stem}_detailed.json"
    with open(detailed_file, 'w', encoding='utf-8') as f:
        json.dump(results['detailed_results'], f, indent=2)
    
    print(f"✓ Saved detailed results to {detailed_file}")


def run_evaluation(input_dir: str = "generated_tests",
                  model: Optional[str] = None,
                  output_file: str = "evaluation_results.json",
                  log_file: str = "evaluation_debug.log",
                  measure_coverage: bool = True,
                  extract_tests: bool = True):
    """
    Main function to run evaluation
    
    Args:
        input_dir: Directory containing generated tests
        model: Optional model name to filter by
        output_file: Output file for results
        log_file: Log file for detailed debugging information
        measure_coverage: Whether to measure code coverage
        extract_tests: Whether to extract test code from markdown
    """
    # Clear log file
    Path(log_file).unlink(missing_ok=True)
    
    print("="*60)
    print("LLM Test Evaluation")
    print("="*60)
    print(f"Debug log: {log_file}")
    print()
    
    # Load tests
    language_data, generated_responses = load_tests_from_directory(input_dir, model)
    
    if not language_data:
        print("\nNo test data found!")
        return
    
    # Run evaluation
    print(f"\n{'='*60}")
    print("Running Evaluation")
    print(f"{'='*60}\n")
    
    results = evaluate_llm_test_generations(
        language_data=language_data,
        generated_responses=generated_responses,
        measure_coverage=measure_coverage,
        extract_tests=extract_tests,
        log_file=log_file
    )
    
    # Print summary
    print(f"\n{'='*60}")
    print("Evaluation Summary")
    print(f"{'='*60}")
    print(f"Total tests evaluated: {results['total_evaluated']}")
    print(f"Total tests passed: {results['total_tests_passed']}")
    
    if results['total_evaluated'] > 0:
        overall_rate = results['total_tests_passed'] / results['total_evaluated'] * 100
        print(f"Overall pass rate: {overall_rate:.2f}%")
    
    print(f"\nPass rates by language:")
    for lang, rate in results['test_pass_rates'].items():
        print(f"  {lang}: {rate*100:.2f}%")
    
    if results['coverage_stats']:
        print(f"\nCoverage statistics:")
        for lang, stats in results['coverage_stats'].items():
            print(f"  {lang}:")
            print(f"    Average: {stats['average']:.2f}%")
            print(f"    Min: {stats['min']:.2f}%")
            print(f"    Max: {stats['max']:.2f}%")
    
    # Save results
    save_evaluation_results(results, output_file)
    
    print(f"\n{'='*60}")
    print("Evaluation Complete!")
    print(f"{'='*60}\n")
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Evaluate LLM-generated tests")
    parser.add_argument(
        "--input-dir",
        default="generated_tests",
        help="Directory containing generated tests (default: generated_tests)"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Filter by specific model (e.g., gpt-4, glm-4.7)"
    )
    parser.add_argument(
        "--output",
        default="evaluation_results.json",
        help="Output file for results (default: evaluation_results.json)"
    )
    parser.add_argument(
        "--log",
        default="evaluation_debug.log",
        help="Log file for debugging (default: evaluation_debug.log)"
    )
    parser.add_argument(
        "--no-coverage",
        action="store_true",
        help="Disable coverage measurement"
    )
    parser.add_argument(
        "--no-extract",
        action="store_true",
        help="Disable test extraction from markdown"
    )
    
    args = parser.parse_args()
    
    run_evaluation(
        input_dir=args.input_dir,
        model=args.model,
        output_file=args.output,
        log_file=args.log,
        measure_coverage=not args.no_coverage,
        extract_tests=not args.no_extract
    )
