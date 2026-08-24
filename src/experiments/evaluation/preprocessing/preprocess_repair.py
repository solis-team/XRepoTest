#!/usr/bin/env python3
"""
Preprocess iterative repair responses for evaluation.

Converts repair outputs from responses folder into evaluation-ready format in results folder.
Handles the difference between repair output format (response as string) and evaluation input format (response as list).

Input:  data/responses/{lang}/{mode}/{model}/repair/prompts_responses_attempt{N}.jsonl
Output: data/results/{lang}/{mode}/{model}/processed_iterative_repair_attemptN.jsonl

Usage:
    # Process single repair attempt
    python preprocess_repair.py --lang go --mode file_context --model gpt-5.2 --attempt 1
    
    # Explicit paths
    python preprocess_repair.py --input /path/to/prompts_responses_attempt1.jsonl --output /path/to/processed.jsonl
    
    # Batch processing (all models in a mode)
    python preprocess_repair.py --lang go --mode file_context --attempt 1

Format Conversion:
    Input:  {"task_id": 0, "response": "raw markdown with code fences"}  # Raw LLM output
    Output: {"task_id": 0, "response": ["extracted_test_code"]}           # Extracted code blocks

    - Extracts code from markdown fences via extract_code_from_markdown()
    - Converts string response to list (required by evaluation system)
    - Maintains task_id mapping for downstream evaluation
    - Preserves all responses, including errors (evaluation handles them)
    
Note: Uses shared preprocess_file_to_output() which calls extract_code_from_markdown()
to extract code blocks from raw LLM responses (matching the generation pipeline).
"""

import json
import argparse
from pathlib import Path

from experiments.evaluation.common.constants import SUPPORTED_LANGUAGES
from experiments.evaluation.preprocessing.preprocess_utils import (
    derive_default_output_path,
    preprocess_file_to_output,
)


def _normalize_model_dir(model_name: str) -> str:
    """Normalize model names to match generation output folder naming."""
    return model_name.replace("/", "_").replace(":", "_")


def process_repair_file(input_path: Path, output_path: Path, verbose: bool = True) -> bool:
    """Process a single repair response file using shared preprocessing utilities.

    Delegates to preprocess_file_to_output() which does:
    load JSONL -> extract_code_from_markdown() -> normalize_response_payload() -> write JSONL

    Args:
        input_path: Path to prompts_responses_attempt{N}.jsonl (raw LLM markdown)
        output_path: Path to output processed file
        verbose: Print progress messages
    """
    if verbose:
        print(f"Reading from {input_path}...")
        print(f"Writing to {output_path}...")

    try:
        preprocess_file_to_output(
            input_path=input_path,
            output_path=output_path,
            drop_prompt=True,
        )
    except FileNotFoundError:
        print(f"❌ Error: Input file not found: {input_path}")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in input file - {e}")
        return False
    except Exception as e:
        print(f"❌ Error processing file: {e}")
        return False

    if verbose:
        print(f"✅ Successfully processed output saved to {output_path}")

    return True


def discover_and_process(lang: str, mode: str, model: str, attempt: int, base_dir: Path, verbose: bool = True):
    """Discover repair response files and process them
    
    Args:
        lang: Language (go, rust, julia, php, ruby)
        mode: Prompt mode (standard, lsp_context, file_context, rag_bm25, rag_dense)
        model: Model name (or None for all models)
        attempt: Repair attempt number
        base_dir: Base evaluation directory
        verbose: Print progress messages
    """
    responses_dir = base_dir / "data" / "responses" / lang / mode
    
    if not responses_dir.exists():
        print(f"❌ Error: Responses directory not found: {responses_dir}")
        return False
    
    # Determine which models to process
    if model:
        model_dirs = [responses_dir / _normalize_model_dir(model)]
    else:
        model_dirs = [d for d in responses_dir.iterdir() if d.is_dir()]
    
    success_count = 0
    total_count = 0
    
    for model_dir in sorted(model_dirs):
        if not model_dir.is_dir():
            continue
        
        model_name = model_dir.name
        total_count += 1
        
        # Input file path (in responses folder, under repair/ subfolder)
        repair_dir = model_dir / "repair"
        input_filename = f"prompts_responses_attempt{attempt}.jsonl"
        input_path = repair_dir / input_filename
        
        if not input_path.exists():
            if verbose:
                print(f"⏭️  Skipping {lang}/{mode}/{model_name}: Input file not found")
            continue
        
        # Output file path (in results folder)
        output_dir = base_dir / "data" / "results" / lang / mode / model_name
        output_filename = f"processed_iterative_repair_attempt{attempt}.jsonl"
        output_path = output_dir / output_filename
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"Processing: {lang}/{mode}/{model_name}")
            print(f"Attempt: {attempt}")
            print(f"{'='*70}")
        
        # Process the file
        if process_repair_file(input_path, output_path, verbose):
            success_count += 1
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"Batch Processing Complete")
        print(f"Successful: {success_count}/{total_count}")
        print(f"{'='*70}")
    
    return success_count > 0


def main():
    parser = argparse.ArgumentParser(
        description="Preprocess iterative repair responses for evaluation"
    )
    
    # Option 1: Explicit paths
    parser.add_argument(
        "--input",
        type=str,
        help="Explicit input file path"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Explicit output file path"
    )
    
    # Option 2: Auto-discovery based on language/mode/model
    parser.add_argument(
        "--lang",
        type=str,
        choices=list(SUPPORTED_LANGUAGES),
        help="Programming language"
    )
    parser.add_argument(
        "--mode",
        type=str,
        help="Prompt mode (standard, lsp_context, file_context, rag_bm25, rag_dense)"
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Model name (if omitted, processes all models in the mode)"
    )
    parser.add_argument(
        "--attempt",
        type=int,
        default=1,
        help="Repair attempt number (default: 1)"
    )
    
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress messages"
    )
    
    args = parser.parse_args()
    
    verbose = not args.quiet
    
    # Determine base directory (evaluation folder)
    eval_dir = Path(__file__).parent.parent
    
    # Mode 1: Explicit input/output paths
    if args.input and args.output:
        input_path = Path(args.input)
        output_path = Path(args.output)
        
        if not input_path.exists():
            print(f"❌ Error: Input file not found: {input_path}")
            return 1
        
        success = process_repair_file(input_path, output_path, verbose)
        return 0 if success else 1
    
    # Mode 2: Explicit single file with auto output path
    elif args.input:
        input_path = Path(args.input)
        
        if not input_path.exists():
            print(f"❌ Error: Input file not found: {input_path}")
            return 1
        
        output_path = derive_default_output_path(
            input_path,
            filename_replacements=(
                ("prompts_responses_attempt", "processed_iterative_repair_attempt"),
                ("prompts_responses", "processed"),
            ),
            fallback_filename=input_path.name.replace("prompts_responses", "processed"),
        )
        
        success = process_repair_file(input_path, output_path, verbose)
        return 0 if success else 1
    
    # Mode 3: Auto-discovery by lang/mode/model
    elif args.lang and args.mode:
        success = discover_and_process(
            lang=args.lang,
            mode=args.mode,
            model=args.model,
            attempt=args.attempt,
            base_dir=eval_dir,
            verbose=verbose
        )
        return 0 if success else 1
    
    else:
        print("❌ Error: Must provide either:")
        print("  1. --input and --output for explicit file paths")
        print("  2. --input for auto output path")
        print("  3. --lang and --mode for auto-discovery")
        parser.print_help()
        return 1


if __name__ == "__main__":
    exit(main())
