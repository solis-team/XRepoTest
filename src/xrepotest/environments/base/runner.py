"""
Shared runner for language-specific evaluation environments.
"""

import argparse
import json
import os
import copy
from pathlib import Path
from typing import Type, List, Dict, Any, Optional, Callable

from .evaluator import BaseEvaluator

def default_dataset_loader(language: str) -> List[Dict[str, Any]]:
    """Default loader using JSONL files in xrepotest/ directory."""
    # Try local xrepotest directory first (standard for Docker container)
    dataset_path = f"xrepotest/{language}_functions.jsonl"
    
    if not os.path.exists(dataset_path):
        # Try parent directory if running from within a language environment
        # e.g., src/xrepotest/environments/go/
        dataset_path = f"../xrepotest/{language}_functions.jsonl"
        
    if not os.path.exists(dataset_path):
        # Absolute fallback for development from project root
        dataset_path = f"src/xrepotest/environments/xrepotest/{language}_functions.jsonl"
    
    with open(dataset_path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]

def run_environment(
    language: str, 
    evaluator_class: Type[BaseEvaluator],
    dataset_loader: Optional[Callable[[str], List[Dict[str, Any]]]] = None
):
    """
    Common entry point for language-specific evaluations.
    
    Args:
        language: Language identifier (go, rust, julia, php, ruby)
        evaluator_class: The Evaluator class to instantiate
        dataset_loader: Optional custom function to load the base dataset
    """
    parser = argparse.ArgumentParser(
        description=f"Evaluate {language.capitalize()} dataset for compilation and test coverage."
    )

    parser.add_argument(
        "--dataset_dir", type=str, required=True, help="Path to the generated responses JSONL file."
    )
    parser.add_argument(
        "--output_summary",
        type=str,
        default=None,
        help="Output file for evaluation summary JSON.",
    )
    parser.add_argument(
        "--output_data_dir",
        type=str,
        default=None,
        help="Output file for detailed results JSONL.")
    parser.add_argument(
        "--enable_mutation",
        action="store_true",
        default=False,
        help=f"Enable mutation testing for {language}.")

    args = parser.parse_args()
    
    # Load the base dataset
    loader = dataset_loader or default_dataset_loader
    try:
        base_dataset = loader(language)
    except Exception as e:
        print(f"Error loading base dataset for {language}: {e}")
        return

    # Load the generated responses
    try:
        with open(args.dataset_dir, "r", encoding="utf-8") as file:
            response_data = [json.loads(line) for line in file]
    except Exception as e:
        print(f"Error loading response dataset from {args.dataset_dir}: {e}")
        return

    # Build task_id lookup for base dataset
    base_by_task_id = {s["task_id"]: s for s in base_dataset}

    # Filter and merge responses into the dataset
    filtered_dataset = []
    seen_task_ids = set()

    for i, item in enumerate(response_data):
        task_id = item.get("task_id")
        if task_id is None:
            task_id = i

        # Skip duplicates if any
        if task_id in seen_task_ids:
            print(f"Warning: Duplicate task_id {task_id} found, skipping...")
            continue
        seen_task_ids.add(task_id)

        responses = item.get("response", [])

        # Get the corresponding sample from base dataset by task_id
        if task_id in base_by_task_id:
            sample = copy.deepcopy(base_by_task_id[task_id])
            sample["test"] = responses
            filtered_dataset.append(sample)
        else:
            print(f"Warning: task_id {task_id} not found in base dataset.")

    if not filtered_dataset:
        print("No samples to evaluate.")
        return

    # Initialize evaluator and run evaluation
    evaluator = evaluator_class()
    dataset_with_results, summary = evaluator.evaluate_dataset(
        filtered_dataset, 
        enable_mutation_testing=args.enable_mutation
    )

    # Determine output paths
    dataset_path = Path(args.dataset_dir)
    output_summary_path = args.output_summary or str(dataset_path.parent / "summary.json")
    output_results_path = args.output_data_dir or str(dataset_path.parent / "detailed_results.jsonl")

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_results_path), exist_ok=True)

    # Write summary
    with open(output_summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4)

    # Write detailed results
    with open(output_results_path, "w", encoding="utf-8") as f:
        for example in dataset_with_results:
            # Convert any bytes in logs list to strings for JSON serialization
            if "logs" in example and isinstance(example["logs"], list):
                example["logs"] = [
                    log.decode("utf-8") if isinstance(log, bytes) else log
                    for log in example["logs"]
                ]
            f.write(json.dumps(example, ensure_ascii=False) + "\n")

    print(f"\nEvaluation complete for {language}!")
    print(f"  Summary: {output_summary_path}")
    print(f"  Detailed results: {output_results_path}")
