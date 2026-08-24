#!/usr/bin/env python3
"""
Standalone Repair System for xrepotest Test Generation

Post-evaluation repair tool that reads detailed_results.jsonl from evaluation,
generates repaired tests using LLMs, and outputs to responses folder for re-evaluation.
"""

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List, Any

from experiments.evaluation.cache.manager import CacheManager
from xrepotest.config import API_BASE_URL
from experiments.evaluation.llm.openai_client import OpenAIClient
from experiments.evaluation.repair.engine import RepairEngine
from experiments.evaluation.common.constants import SUPPORTED_LANGUAGES


def load_evaluation_results(input_path: str) -> List[Dict[str, Any]]:
    """Load evaluation results from detailed_results.jsonl."""
    samples = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    
    print(f"Loaded {len(samples)} samples from {input_path}")
    return samples


def get_attempt_output_path(output_dir: str, attempt: int) -> str:
    """Generate the output file path for a given repair attempt."""
    return os.path.join(
        output_dir,
        f"prompts_responses_attempt{attempt}.jsonl"
    )


def save_repair_metadata(
    repair_summary: Dict[str, Any],
    output_dir: str,
    args: argparse.Namespace
):
    """Save repair metadata and statistics for this attempt."""
    metadata_path = Path(output_dir) / f"repair_metadata_attempt{args.attempt}.json"
    
    metadata = {
        "repair_config": {
            "language": args.language,
            "attempt": args.attempt,
            "max_attempts": args.max_attempts,
            "repair_model": args.repair_model,
            "repair_provider": args.repair_provider,
            "base_url": args.base_url
        },
        "input_results": args.input_results,
        "output_dir": output_dir,
        "summary": repair_summary
    }
    
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)
    
    print(f"Repair metadata saved to: {metadata_path}")


def print_repair_summary(repair_summary: Dict[str, Any], attempt: int):
    """Print repair summary to console."""
    print(f"\n{'='*70}")
    print(f"REPAIR SUMMARY — Attempt {attempt}")
    print(f"{'='*70}")
    print(f"Total Samples:      {repair_summary.get('total_samples', 0)}")
    print(f"Repaired Count:     {repair_summary.get('repaired_count', 0)}")
    print(f"{'='*70}\n")


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(description="Standalone repair system for xrepotest test generation")
    
    # Input/Output
    parser.add_argument("--input_results", type=str, required=True, help="Path to evaluation results")
    parser.add_argument("--output_dir", type=str, required=True, help="Directory to save per-attempt outputs")
    
    # Language
    parser.add_argument("--language", type=str, required=True, choices=list(SUPPORTED_LANGUAGES), help="Programming language")
    
    # Repair configuration
    parser.add_argument("--attempt", type=int, default=1, help="Current repair attempt number (1-indexed)")
    parser.add_argument("--max_attempts", type=int, default=3, help="Maximum total attempts allowed")
    parser.add_argument("--concurrency", type=int, default=20, help="Number of concurrent repair threads")
    
    # LLM configuration
    parser.add_argument("--repair_model", type=str, default="gpt-4", help="LLM model to use for repair")
    parser.add_argument("--repair_provider", type=str, default="openai", help="LLM provider")
    parser.add_argument("--base_url", type=str, default=None, help="Optional base URL for OpenAI-compatible API")
    parser.add_argument("--api_key", type=str, default=None, help="API key (if not set in environment)")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    parser.add_argument("--delay", type=float, default=0.0, help="Delay between API calls in seconds")
    parser.add_argument("--max_retries", type=int, default=3, help="Maximum number of retry attempts")
    parser.add_argument("--retry_delay", type=float, default=5.0, help="Initial retry delay in seconds")

    return parser


def run_repair(args: argparse.Namespace) -> int:
    """Execute the repair logic."""
    if not os.path.exists(args.input_results):
        print(f"❌ Error: Input file not found: {args.input_results}")
        return 1
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    print(f"\n{'='*70}\nREPAIR ATTEMPT {args.attempt}/{args.max_attempts}\n{'='*70}")
    print(f"Language:     {args.language}")
    print(f"Repair model: {args.repair_model}")
    print(f"Input:        {args.input_results}\n")
    
    try:
        # Initialize components
        base_url = args.base_url or API_BASE_URL
        if not base_url:
            print("❌ Error: No API base URL set. Set API_BASE_URL in xrepotest/config.py or pass --base_url.")
            return 1
        llm_client = OpenAIClient(
            api_key=args.api_key,
            base_url=base_url,
            delay=args.delay,
            max_retries=args.max_retries,
            retry_delay=args.retry_delay,
        )
        
        cache_manager = CacheManager()
        repair_engine = RepairEngine(
            language=args.language,
            llm_client=llm_client,
            model=args.repair_model,
            temperature=args.temperature,
            max_workers=args.concurrency
        )
        
        # Process results
        current_results = load_evaluation_results(args.input_results)
        for i, sample in enumerate(current_results):
            if 'task_id' not in sample:
                sample['task_id'] = i
        
        attempt_output = get_attempt_output_path(args.output_dir, args.attempt)
        existing_results = cache_manager.load_existing_results(attempt_output)
        samples_to_process = cache_manager.filter_prompts(current_results, existing_results)
        
        if not samples_to_process:
            print("  No samples need repair (already processed).")
            return 0
        
        repaired_samples, repair_summary = repair_engine.repair_single_pass(
            samples_to_process,
            attempt_number=args.attempt,
            on_result=lambda sample: cache_manager.append_result(attempt_output, sample),
        )

        print_repair_summary(repair_summary, args.attempt)
        # Results were already persisted incrementally via on_result as each
        # future completed; only the final sort/atomic-rewrite pass remains.
        cache_manager.deduplicate_file(attempt_output)
        save_repair_metadata(repair_summary, args.output_dir, args)
        
        print(f"✅ REPAIR ATTEMPT COMPLETED: {attempt_output}\n")
        return 0
        
    except Exception as exc:
        print(f"\n❌ Error during repair: {exc}")
        return 1


def main():
    parser = build_parser()
    args = parser.parse_args()
    return run_repair(args)


if __name__ == "__main__":
    import sys
    sys.exit(main())
