#!/usr/bin/env python3
"""
Top-level evaluation runner for xrepotest benchmark.
Runs language-specific evaluation for a given model.

Usage:
    python run_evaluation.py --lang go --mode standard --model deepseek-r1-distill-llama-70b
    python run_evaluation.py --lang php --mode file_context --model glm-4.7 --enable_mutation
    python run_evaluation.py --lang rust --mode lsp_context  # Runs all models in that mode
    
    # Custom output (for repair iteration):
    python run_evaluation.py ... --input_file prompts_responses_iterative_repair_attempt1.jsonl --output_file detailed_results_repair_attempt_1.jsonl
"""

import argparse
import subprocess
import sys
from pathlib import Path

from experiments.evaluation.common.constants import (
    LANGUAGE_DOCKER_IMAGES,
    MUTATION_SUPPORTED_LANGS,
    SUPPORTED_LANGUAGES,
)
from experiments.evaluation.common.runner import (
    print_discovery_count,
    print_discovery_intro,
    print_mode_model_summary,
)
from experiments.evaluation.common.task_discovery import discover_mode_model_tasks


def _normalize_model_dir(model_name: str) -> str:
    """Normalize model names to match generation output folder naming."""
    return model_name.replace("/", "_").replace(":", "_")


def main():
    parser = argparse.ArgumentParser(
        description="Run xrepotest evaluation for a specific language and model"
    )
    parser.add_argument(
        "--lang",
        type=str,
        required=True,
        choices=list(SUPPORTED_LANGUAGES),
        help="Programming language to evaluate"
    )
    parser.add_argument(
        "--mode",
        type=str,
        default=None,
        help="Prompt mode (e.g., standard, lsp_context, file_context, rag_bm25, rag_dense). If not specified, runs all modes."
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name (folder name under results/{lang}/{mode}/). If not specified, runs all models."
    )
    parser.add_argument(
        "--enable_mutation",
        action="store_true",
        help="Enable mutation testing where supported by the evaluator"
    )
    parser.add_argument(
        "--input_file",
        type=str,
        default="processed.jsonl",
        help="Input filename (default: processed.jsonl)"
    )
    parser.add_argument(
        "--output_file",
        type=str,
        default="detailed_results.jsonl",
        help="Output detailed results filename (default: detailed_results.jsonl)"
    )
    
    args = parser.parse_args()
    
    # Base directories
    eval_dir = Path(__file__).parent
    data_dir = eval_dir / "data"
    
    # Determine which modes and models to evaluate
    lang_base_dir = data_dir / "results" / args.lang

    # If processed results missing, don't batch-preprocess the whole language.
    # Instead, allow per-model on-demand preprocessing from data/responses/{lang}.
    responses_lang_dir = data_dir / "responses" / args.lang
    if not lang_base_dir.exists():
        if not responses_lang_dir.exists():
            print(f"❌ Error: No processed input directory found for {args.lang}: {lang_base_dir}")
            return 1
        print(f"⚠️  No processed results found for {args.lang}. Will preprocess missing models on demand from: {responses_lang_dir}")

    print_discovery_intro(
        mode=args.mode,
        model=args.model,
        lang_base_dir=lang_base_dir,
        eval_dir=eval_dir,
    )

    try:
        tasks_to_evaluate = discover_mode_model_tasks(
            lang_base_dir=lang_base_dir,
            mode=args.mode,
            model=args.model,
        )
    except ValueError as exc:
        print(f"❌ Error: {exc}")
        return 1

    print_discovery_count(
        mode=args.mode,
        model=args.model,
        task_count=len(tasks_to_evaluate),
    )
    
    # Track results
    evaluated = []
    skipped = []
    failed = []
    
    for mode, model_name in tasks_to_evaluate:
        model_dir = _normalize_model_dir(model_name)
        # Construct path
        model_path = lang_base_dir / mode / model_dir
        input_path = model_path / args.input_file
        
        # Summary path changes based on whether we are repairing or not
        # Ideally summary should also correspond to the attempt, but the backend script
        # currently might generate a fixed summary name.
        # For now, let's assume we rely on detailed_results existence.
        output_detailed_path = model_path / args.output_file
        
        # Check if input file exists — if missing, try on-demand preprocessing from responses/
        if not input_path.exists():
            # Attempt to find corresponding responses file
            responses_file = None
            responses_model_dir = data_dir / "responses" / args.lang / mode / model_dir
            # Backward-compatibility fallback for already-normalized task discovery inputs.
            if not responses_model_dir.exists() and model_name != model_dir:
                alt_dir = data_dir / "responses" / args.lang / mode / model_name
                if alt_dir.exists():
                    responses_model_dir = alt_dir

            # Common filename
            candidate = responses_model_dir / "prompts_responses.jsonl"
            if candidate.exists():
                responses_file = candidate
            else:
                # Fallback: any file matching '*responses.jsonl' in model dir
                if responses_model_dir.exists():
                    for p in responses_model_dir.glob("*responses.jsonl"):
                        responses_file = p
                        break
                # Also search repair/ subfolder for repair response files
                if responses_file is None:
                    repair_dir = responses_model_dir / "repair"
                    if repair_dir.exists():
                        for p in sorted(repair_dir.glob("prompts_responses_*.jsonl"), reverse=True):
                            responses_file = p
                            break

            if responses_file and responses_file.exists():
                print(f"⚠️  Processed input missing for {mode}/{model_name}, preprocessing from: {responses_file.relative_to(data_dir)}")
                # Import here to avoid hard dependency if preprocessing module missing
                try:
                    from experiments.evaluation.preprocessing.preprocess_utils import (
                        preprocess_file_to_output,
                    )
                    # Ensure destination dir exists
                    input_path.parent.mkdir(parents=True, exist_ok=True)
                    preprocess_file_to_output(
                        input_path=responses_file,
                        output_path=input_path,
                        drop_prompt=True,
                    )
                    print(f"   ✅ Preprocessed: {input_path.relative_to(data_dir)}")
                except (ImportError, OSError, ValueError) as exc:
                    print(f"   ❌ Failed to preprocess {responses_file}: {exc}")
                    skipped.append((mode, model_name, "preprocess failed"))
                    continue
            else:
                print(f"⚠️  Skipping {mode}/{model_name}: Input file not found ({args.input_file})")
                skipped.append((mode, model_name, "input file not found"))
                continue
        
        # Check if already evaluated (simplistic check based on output file existence)
        # Note: If reusing standard summary.json, we might false-skip if it exists from previous runs.
        # But here we check the DETAILED output, which varies by name.
        if output_detailed_path.exists():
             print(f"⏭️  Skipping {mode}/{model_name}: Already evaluated ({args.output_file} exists)")
             skipped.append((mode, model_name, "already evaluated"))
             continue
        
        # Run evaluation for this model
        result = run_single_evaluation(
            lang=args.lang,
            mode=mode,
            model=model_dir,
            input_path=input_path,
            output_filename=args.output_file,  # Pass just filename, path constructed relative to docker mount
            data_dir=data_dir,
            eval_dir=eval_dir,
            enable_mutation=args.enable_mutation
        )
        
        if result == 0:
            evaluated.append((mode, model_name))
        else:
            failed.append((mode, model_name))
    
    return print_mode_model_summary(
        title=f"Evaluation Summary for {args.lang}",
        success_label="Evaluated",
        success_items=evaluated,
        skipped_items=skipped,
        failed_items=failed,
    )


def _derive_summary_filename(output_filename: str) -> str:
    """Derive the summary JSON filename from the detailed-results filename.

    Convention:
      detailed_results.jsonl              → summary.json
      detailed_results_<suffix>.jsonl     → summary_<suffix>.json
      <other_name>.jsonl                  → summary_<other_name>.json
    """
    if output_filename == "detailed_results.jsonl":
        return "summary.json"
    stem = Path(output_filename).stem
    if stem.startswith("detailed_results_"):
        suffix = stem[len("detailed_results_"):]
        return f"summary_{suffix}.json"
    return f"summary_{stem}.json"


def run_single_evaluation(lang, mode, model, input_path, output_filename, data_dir, eval_dir, enable_mutation):
    """Run evaluation for a single model"""
    
    image_name = LANGUAGE_DOCKER_IMAGES[lang]
    
    print(f"\n{'='*80}")
    print("Running xrepotest Evaluation")
    print(f"  Language: {lang}")
    print(f"  Mode: {mode}")
    print(f"  Model: {model}")
    print(f"  Input: {input_path.relative_to(eval_dir)}")
    print(f"  Output: {output_filename}")
    if enable_mutation:
        print(f"  Mutation Testing: {'ENABLED' if lang in MUTATION_SUPPORTED_LANGS else 'NOT SUPPORTED'}")
    print(f"{'='*80}\n")
    
    # Construct paths relative to data directory for Docker mount
    input_filename = input_path.name
    input_rel = f"results/{lang}/{mode}/{model}/{input_filename}"
    output_parent = f"results/{lang}/{mode}/{model}"
    
    # Docker paths (inside container)
    docker_input = f"/data/{input_rel}"
    summary_filename = _derive_summary_filename(output_filename)
    docker_summary = f"/data/{output_parent}/{summary_filename}"
    docker_detailed = f"/data/{output_parent}/{output_filename}"
    
    # Build Docker command
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{data_dir.absolute()}:/data",
        image_name,
        "python3", "/app/main.py",
        "--dataset_dir", docker_input,
        "--output_summary", docker_summary,
        "--output_data_dir", docker_detailed
    ]
    
    # Add mutation flag if supported and requested
    if enable_mutation and lang in MUTATION_SUPPORTED_LANGS:
        cmd.append("--enable_mutation")
    
    print(f">>> Running Docker container: {image_name}")
    print(f"    Input: {docker_input}")
    print(f"    Output (Detailed): {output_parent}/{output_filename}")
    print(f"    Output (Summary):  {output_parent}/{summary_filename}")
    if enable_mutation and lang in MUTATION_SUPPORTED_LANGS:
        print("    Mutation testing: ENABLED")
    print()
    
    # Run the Docker evaluation
    try:
        result = subprocess.run(cmd, check=False)
        
        if result.returncode == 0:
            output_dir = input_path.parent
            print(f"\n{'='*80}")
            print("✅ Evaluation completed successfully!")
            print(f"   Results saved to: {output_dir.relative_to(eval_dir)}")
            print(f"     - {summary_filename}")
            print(f"     - {output_filename}")
            return 0
        else:
            print(f"\n❌ Evaluation failed with exit code {result.returncode}")
            return result.returncode
            
    except (OSError, ValueError) as exc:
        print(f"\n❌ Error running evaluation: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
