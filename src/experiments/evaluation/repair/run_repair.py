#!/usr/bin/env python3
"""
Top-level repair runner for xrepotest benchmark.
Runs repair on evaluation results for a given language and model.

Repair Approach:
    - Minimal context: Only failed_test + error_log sent to LLM
    - No focal code, file context, or LSP enrichment
    - Fast, focused error-driven repair

Input/Output:
    Input:  data/results/{lang}/{mode}/{model}/detailed_results.jsonl
    Output: data/responses/{lang}/{mode}/{model}/repair/prompts_responses_attempt{N}.jsonl
    
Output Format:
    {"task_id": "...", "prompt": "...", "response": "test_code_string", "status": "success|error"}
    - "status" is "success" or "error" (uses result_contract conventions)
    - "prompt" contains the repair prompt text sent to the LLM
    - "response" is a string (like oneshot generation)
    - If repair succeeds: repaired test code with status "success"
    - If repair fails: error message with status "error" (filtered by cache manager for retry)
    - Ready for preprocessing and re-evaluation

Usage:
    python run_repair.py --lang go --mode standard --model deepseek-r1-distill-llama-70b --attempt 1
    python run_repair.py --lang php --mode file_context --attempt 2
    
    # Auto-detects input file based on attempt:
    # Attempt 1 -> reads detailed_results.jsonl
    # Attempt 2 -> reads detailed_results_repair_attempt_1.jsonl
    
Workflow:
    1. Run repair (attempt N) -> generates prompts_responses_attempt{N}.jsonl in responses/<model>/repair/ folder
    2. Preprocess and run evaluation -> generates detailed_results_repair_attempt_N.jsonl in results folder
    3. Repeat for next attempt if needed
"""

import argparse
import sys
from argparse import Namespace
from pathlib import Path

from experiments.evaluation.common.constants import SUPPORTED_LANGUAGES
from experiments.evaluation.common.runner import (
    print_discovery_count,
    print_discovery_intro,
    print_mode_model_summary,
)
from experiments.evaluation.common.task_discovery import discover_mode_model_tasks
from experiments.evaluation.repair.repair_cli import run_repair as run_repair_cli


def main():
    parser = argparse.ArgumentParser(
        description="Run xrepotest repair for a specific language and model"
    )
    parser.add_argument(
        "--lang",
        type=str,
        required=True,
        choices=list(SUPPORTED_LANGUAGES),
        help="Programming language to repair"
    )
    parser.add_argument(
        "--mode",
        type=str,
        default=None,
        help="Prompt mode (e.g., standard, lsp_context, file_context, rag_bm25, rag_dense). If not specified, repairs all modes."
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name (folder name under results/{lang}/{mode}/). If not specified, repairs all models."
    )
    parser.add_argument(
        "--attempt",
        type=int,
        default=1,
        help="Repair attempt number (default: 1). Input file is automatically determined based on this."
    )
    parser.add_argument(
        "--max_attempts",
        type=int,
        default=3,
        help="Maximum repair attempts per failed test (passed to repair engine context)"
    )
    parser.add_argument(
        "--repair_model",
        type=str,
        default="gpt-4",
        help="LLM model to use for repair (default: gpt-4)"
    )
    parser.add_argument(
        "--repair_provider",
        type=str,
        default="openai",
        help="LLM provider (currently only 'openai' supported)"
    )
    parser.add_argument(
        "--base_url",
        type=str,
        default=None,
        help="Optional base URL for OpenAI-compatible API"
    )
    parser.add_argument(
        "--api_key",
        type=str,
        default=None,
        help="API key (defaults to xrepotest.config.API_KEY)"
    )
    parser.add_argument(
        "--input_results",
        type=str,
        default=None,
        help="Explicitly override input file path (otherwise auto-determined)"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=20,
        help="Number of concurrent repair threads (default: 20)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay between API calls in seconds (default: 0.0)"
    )
    parser.add_argument(
        "--max_retries",
        type=int,
        default=3,
        help="Maximum number of retry attempts (default: 3)"
    )
    parser.add_argument(
        "--retry_delay",
        type=float,
        default=5.0,
        help="Initial retry delay in seconds (default: 5.0)"
    )
    args = parser.parse_args()

    # --model identifies an on-disk results/responses folder, which generate_responses.py
    # and xrepotest.cli._sanitize_model_name write with "/" and ":" replaced by "_".
    # Sanitize here too so raw model ids (e.g. "workers-ai/@cf/openai/gpt-oss-120b") resolve
    # to the same folder instead of being treated as nested path segments.
    if args.model:
        args.model = args.model.replace("/", "_").replace(":", "_")

    # Base directories
    eval_dir = Path(__file__).parent.parent
    data_dir = eval_dir / "data"
    results_base_dir = data_dir / "results" / args.lang  # Input from results
    responses_base_dir = data_dir / "responses" / args.lang  # Output to responses

    if not results_base_dir.exists():
        print(f"❌ Error: No results directory found for {args.lang}: {results_base_dir}")
        return 1

    print_discovery_intro(
        mode=args.mode,
        model=args.model,
        lang_base_dir=results_base_dir,
        eval_dir=eval_dir,
    )

    try:
        tasks_to_repair = discover_mode_model_tasks(
            lang_base_dir=results_base_dir,
            mode=args.mode,
            model=args.model,
        )
    except ValueError as exc:
        print(f"❌ Error: {exc}")
        return 1

    print_discovery_count(mode=args.mode, model=args.model, task_count=len(tasks_to_repair))

    # Track results
    repaired = []
    skipped = []
    failed = []

    for mode, model_name in tasks_to_repair:
        # Construct paths
        results_model_dir = results_base_dir / mode / model_name  # Input from results
        responses_model_dir = responses_base_dir / mode / model_name / "repair"  # Output to responses/<model>/repair/

        # Ensure output directory exists
        responses_model_dir.mkdir(parents=True, exist_ok=True)

        # Determine Input File
        if args.input_results:
            input_path = Path(args.input_results)
        else:
            if args.attempt == 1:
                input_path = results_model_dir / "detailed_results.jsonl"
            else:
                input_path = results_model_dir / f"detailed_results_repair_attempt_{args.attempt - 1}.jsonl"

        # Output File (to responses folder)
        output_path = responses_model_dir / f"prompts_responses_attempt{args.attempt}.jsonl"

        # Check if input exists
        if not input_path.exists():
            print(f"⚠️  Skipping {mode}/{model_name}: Input file not found: {input_path.name}")
            skipped.append((mode, model_name, f"input missing: {input_path.name}"))
            continue

        # Run repair for this model (cache manager handles resume/skip logic)
        result = run_single_repair(
            lang=args.lang,
            mode=mode,
            model=model_name,
            input_path=input_path,
            output_path=output_path,
            args=args,
            eval_dir=eval_dir
        )

        if result == 0:
            repaired.append((mode, model_name))
        else:
            failed.append((mode, model_name))

    return print_mode_model_summary(
        title=f"Repair Summary for {args.lang} (Attempt {args.attempt})",
        success_label="Repaired",
        success_items=repaired,
        skipped_items=skipped,
        failed_items=failed,
    )


def run_single_repair(lang, mode, model, input_path, output_path, args, eval_dir):
    """Run repair for a single model (in-process)."""

    print(f"\n{'='*80}")
    print("Running xrepotest Repair")
    print(f"  Language:     {lang}")
    print(f"  Mode:         {mode}")
    print(f"  Model:        {model}")
    print(f"  Attempt:      {args.attempt}")
    print(f"  Input:        {input_path}")
    print(f"  Output:       {output_path.relative_to(eval_dir)}")
    print(f"  Repair model: {args.repair_model}")
    print(f"{'='*80}\n")

    repair_args = Namespace(
        input_results=str(input_path),
        output_dir=str(output_path.parent),
        language=lang,
        attempt=args.attempt,
        max_attempts=args.max_attempts,
        repair_model=args.repair_model,
        repair_provider=args.repair_provider,
        concurrency=args.concurrency,
        base_url=args.base_url,
        api_key=args.api_key,
        temperature=0.0,
        delay=args.delay,
        max_retries=args.max_retries,
        retry_delay=args.retry_delay,
    )

    print(">>> Running repair (in-process)...")
    print()
    return run_repair_cli(repair_args)


if __name__ == "__main__":
    sys.exit(main())
