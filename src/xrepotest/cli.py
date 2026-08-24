"""Unified CLI entrypoint for experiment workflows."""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence

from experiments.evaluation.common.modes import (
    DEFAULT_PROMPT_MODE,
    PROMPT_MODE_CHOICES,
)
from xrepotest.config import (
    RUN_DEFAULT_MAX_WORKERS,
    RUN_RAG_CONTEXT_SIZE_CHOICES,
)
from xrepotest.languages import SUPPORTED_LANGUAGES
from xrepotest.paths import get_evaluation_data_dir
from xrepotest.config import API_BASE_URL

_ENTRYPOINTS = {
    "prompts": "experiments.evaluation.generation.generate_prompts:main",
    "responses": "experiments.evaluation.generation.generate_responses:main",
    "preprocess": "experiments.evaluation.preprocessing.preprocess:main",
    "eval": "experiments.evaluation.run_evaluation:main",
    "repair": "experiments.evaluation.repair.run_repair:main",
    "repair-preprocess": "experiments.evaluation.preprocessing.preprocess_repair:main",
    "agentic": "experiments.evaluation.agentic.run_agentic:main",
}

def _normalize_runtime_language(value: str) -> str:
    key = value.strip().lower()
    if key not in SUPPORTED_LANGUAGES:
        choices = ", ".join(SUPPORTED_LANGUAGES)
        raise argparse.ArgumentTypeError(f"Unsupported language '{value}'. Choose from: {choices}")
    return key


def _append_optional(argv: list[str], flag: str, value: object) -> None:
    if value is None:
        return
    if isinstance(value, str) and value == "":
        return
    argv.extend([flag, str(value)])


def _sanitize_model_name(model_name: str) -> str:
    return model_name.replace("/", "_").replace(":", "_")


def _resolve_mode_dir(mode: str, context_size: int | None, top_k: int | None) -> str:
    if mode in {"rag_bm25", "rag_dense"} and context_size is not None and top_k is not None:
        return f"{mode}_ws{context_size}_k{top_k}"
    return mode


def _run_entrypoint(entrypoint: str, argv: Sequence[str], *, prog: str) -> int:
    module_name, function_name = entrypoint.split(":")
    module = importlib.import_module(module_name)
    main_func = getattr(module, function_name)

    original_argv = sys.argv
    sys.argv = [prog, *argv]
    try:
        result = main_func()
    finally:
        sys.argv = original_argv

    return result if isinstance(result, int) else 0


def _handle_prompts(args: argparse.Namespace) -> int:
    argv = [
        "--split",
        args.split,
        "--lang",
        args.lang,
        "--output_dir",
        args.output_dir,
    ]
    _append_optional(argv, "--mode", args.mode)
    _append_optional(argv, "--context_size", args.context_size)
    _append_optional(argv, "--top_k", args.top_k)
    return _run_entrypoint(_ENTRYPOINTS["prompts"], argv, prog="xrepotest prompts")


def _handle_responses(args: argparse.Namespace) -> int:
    argv = [
        "--model",
        args.model,
        "--input_dir",
        args.input_dir,
        "--api_base",
        args.api_base,
        "--max_workers",
        str(args.max_workers),
        "--delay",
        str(args.delay),
        "--max_retries",
        str(args.max_retries),
        "--retry_delay",
        str(args.retry_delay),
    ]
    _append_optional(argv, "--api_key", args.api_key)
    if args.no_multithreading:
        argv.append("--no_multithreading")
    return _run_entrypoint(_ENTRYPOINTS["responses"], argv, prog="xrepotest responses")


def _handle_preprocess(args: argparse.Namespace) -> int:
    argv = [
        "--input_directory",
        args.input_directory,
        "--max_tests",
        str(args.max_tests),
    ]
    _append_optional(argv, "--output_directory", args.output_directory)
    return _run_entrypoint(_ENTRYPOINTS["preprocess"], argv, prog="xrepotest preprocess")


def _handle_eval(args: argparse.Namespace) -> int:
    argv = [
        "--lang",
        args.lang,
        "--input_file",
        args.input_file,
        "--output_file",
        args.output_file,
    ]
    _append_optional(argv, "--mode", args.mode)
    _append_optional(argv, "--model", args.model)
    if args.enable_mutation:
        argv.append("--enable_mutation")
    return _run_entrypoint(_ENTRYPOINTS["eval"], argv, prog="xrepotest eval")


def _handle_repair(args: argparse.Namespace) -> int:
    argv = [
        "--lang",
        args.lang,
        "--attempt",
        str(args.attempt),
        "--max_attempts",
        str(args.max_attempts),
        "--repair_model",
        args.repair_model,
        "--repair_provider",
        args.repair_provider,
        "--concurrency",
        str(args.concurrency),
        "--delay",
        str(args.delay),
        "--max_retries",
        str(args.max_retries),
        "--retry_delay",
        str(args.retry_delay),
    ]
    _append_optional(argv, "--mode", args.mode)
    _append_optional(argv, "--model", args.model)
    _append_optional(argv, "--base_url", args.base_url)
    _append_optional(argv, "--api_key", args.api_key)
    _append_optional(argv, "--input_results", args.input_results)
    return _run_entrypoint(_ENTRYPOINTS["repair"], argv, prog="xrepotest repair")


def _handle_repair_preprocess(args: argparse.Namespace) -> int:
    argv: list[str] = []
    if args.input:
        argv.extend(["--input", args.input])
        if args.output:
            argv.extend(["--output", args.output])
    elif args.lang and args.mode:
        argv.extend(["--lang", args.lang, "--mode", args.mode])
        _append_optional(argv, "--model", args.model)
        _append_optional(argv, "--attempt", str(args.attempt))
    if args.quiet:
        argv.append("--quiet")
    return _run_entrypoint(_ENTRYPOINTS["repair-preprocess"], argv, prog="xrepotest repair-preprocess")


def _handle_agentic(args: argparse.Namespace) -> int:
    argv = [
        "--lang",
        args.lang,
        "--concurrency",
        str(args.concurrency),
        "--timeout",
        str(args.timeout),
        "--baseline-mode",
        args.baseline_mode,
        "--baseline-model",
        args.baseline_model,
    ]
    _append_optional(argv, "--model", args.model)
    _append_optional(argv, "--output-model-dir", args.output_model_dir)
    _append_optional(argv, "--repo", args.repo)
    _append_optional(argv, "--task-id", args.task_id)
    return _run_entrypoint(_ENTRYPOINTS["agentic"], argv, prog="xrepotest agentic")


def _handle_run(args: argparse.Namespace) -> int:
    is_rag_mode = args.mode in {"rag_bm25", "rag_dense"}
    has_context_size = args.context_size is not None
    has_top_k = args.top_k is not None

    if not is_rag_mode and (has_context_size or has_top_k):
        print("Error: --context_size and --top_k are only valid for rag_bm25 or rag_dense modes.", file=sys.stderr)
        return 2

    if is_rag_mode and has_context_size != has_top_k:
        print("Error: --context_size and --top_k must be provided together for RAG run mode.", file=sys.stderr)
        return 2

    split = args.split if args.split is not None else args.lang
    mode_dir = _resolve_mode_dir(args.mode, args.context_size, args.top_k)
    model_dir = _sanitize_model_name(args.model)
    data_root = get_evaluation_data_dir()

    responses_mode_dir = data_root / "responses" / args.lang / mode_dir
    results_model_dir = data_root / "results" / args.lang / mode_dir / model_dir
    raw_response_path = responses_mode_dir / model_dir / "prompts_responses.jsonl"
    processed_output_path = results_model_dir / "processed.jsonl"

    prompts_argv = [
        "--split",
        split,
        "--lang",
        args.lang,
        "--output_dir",
        str(responses_mode_dir),
        "--mode",
        args.mode,
    ]
    _append_optional(prompts_argv, "--context_size", args.context_size)
    _append_optional(prompts_argv, "--top_k", args.top_k)
    exit_code = _run_entrypoint(_ENTRYPOINTS["prompts"], prompts_argv, prog="xrepotest run (prompts)")
    if exit_code != 0:
        return exit_code

    responses_argv = [
        "--model",
        args.model,
        "--input_dir",
        str(responses_mode_dir),
        "--api_base",
        args.api_base,
        "--max_workers",
        str(args.max_workers),
        "--delay",
        str(args.delay),
        "--max_retries",
        str(args.max_retries),
        "--retry_delay",
        str(args.retry_delay),
    ]
    _append_optional(responses_argv, "--api_key", args.api_key)
    if args.no_multithreading:
        responses_argv.append("--no_multithreading")
    exit_code = _run_entrypoint(_ENTRYPOINTS["responses"], responses_argv, prog="xrepotest run (responses)")
    if exit_code != 0:
        return exit_code

    preprocess_argv = [
        "--input_directory",
        str(raw_response_path),
        "--output_directory",
        str(processed_output_path),
        "--max_tests",
        str(args.max_tests),
    ]
    exit_code = _run_entrypoint(_ENTRYPOINTS["preprocess"], preprocess_argv, prog="xrepotest run (preprocess)")
    if exit_code != 0:
        return exit_code

    eval_argv = [
        "--lang",
        args.lang,
        "--input_file",
        "processed.jsonl",
        "--output_file",
        args.output_file,
        "--mode",
        mode_dir,
        "--model",
        model_dir,
    ]
    if args.enable_mutation:
        eval_argv.append("--enable_mutation")
    return _run_entrypoint(_ENTRYPOINTS["eval"], eval_argv, prog="xrepotest run (eval)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xrepotest",
        description="Unified CLI for xrepotest experiment workflows.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prompts = subparsers.add_parser("prompts", help="Generate prompts")
    prompts.add_argument("--split", type=str, required=True, help="Dataset split")
    prompts.add_argument("--lang", type=_normalize_runtime_language, required=True, help="Language")
    prompts.add_argument("--output_dir", type=str, required=True, help="Output directory for prompts")
    prompts.add_argument("--mode", type=str, choices=PROMPT_MODE_CHOICES, default=None, help="Prompt mode")
    prompts.add_argument(
        "--context_size",
        type=int,
        choices=RUN_RAG_CONTEXT_SIZE_CHOICES,
        default=None,
        help="RAG context window",
    )
    prompts.add_argument("--top_k", type=int, default=None, help="Top-k contexts for RAG")
    prompts.set_defaults(handler=_handle_prompts)

    responses = subparsers.add_parser("responses", help="Generate model responses")
    responses.add_argument("--model", type=str, required=True, help="Model name")
    responses.add_argument("--input_dir", type=str, default="../data/responses", help="Input directory")
    responses.add_argument("--api_key", type=str, default=None, help="API key")
    responses.add_argument(
        "--api_base",
        type=str,
        default=API_BASE_URL,
        help="API base URL (set this in xrepotest/config.py, or override here)",
    )
    responses.add_argument("--max_workers", type=int, default=RUN_DEFAULT_MAX_WORKERS, help="Concurrent workers")
    responses.add_argument("--delay", type=float, default=0.0, help="Delay between API calls")
    responses.add_argument("--max_retries", type=int, default=3, help="Retry attempts")
    responses.add_argument(
        "--retry_delay",
        type=float,
        default=5.0,
        help="Initial retry delay",
    )
    responses.add_argument("--no_multithreading", action="store_true", help="Disable multithreading")
    responses.set_defaults(handler=_handle_responses)

    preprocess = subparsers.add_parser("preprocess", help="Preprocess one response JSONL file")
    preprocess.add_argument("--input_directory", type=str, required=True, help="Input JSONL file path")
    preprocess.add_argument("--output_directory", type=str, default="", help="Output JSONL file path")
    preprocess.add_argument(
        "--max_tests",
        type=int,
        default=10,
        help="Maximum number of tests per sample",
    )
    preprocess.set_defaults(handler=_handle_preprocess)

    run = subparsers.add_parser("run", help="Run prompts -> responses -> preprocess -> eval")
    run.add_argument("--lang", type=_normalize_runtime_language, required=True, help="Language")
    run.add_argument("--model", type=str, required=True, help="Model name for response generation")
    run.add_argument("--mode", type=str, choices=PROMPT_MODE_CHOICES, default=DEFAULT_PROMPT_MODE, help="Prompt mode")
    run.add_argument("--split", type=str, default=None, help="Dataset split for prompt generation")
    run.add_argument(
        "--context_size",
        type=int,
        choices=RUN_RAG_CONTEXT_SIZE_CHOICES,
        default=None,
        help="RAG context window",
    )
    run.add_argument("--top_k", type=int, default=None, help="Top-k contexts for RAG prompts")
    run.add_argument("--api_key", type=str, default=None, help="API key")
    run.add_argument(
        "--api_base",
        type=str,
        default=API_BASE_URL,
        help="API base URL (set this in xrepotest/config.py, or override here)",
    )
    run.add_argument("--max_workers", type=int, default=RUN_DEFAULT_MAX_WORKERS, help="Concurrent workers")
    run.add_argument("--delay", type=float, default=0.0, help="Delay between API calls")
    run.add_argument("--max_retries", type=int, default=3, help="Retry attempts")
    run.add_argument(
        "--retry_delay",
        type=float,
        default=5.0,
        help="Initial retry delay",
    )
    run.add_argument("--no_multithreading", action="store_true", help="Disable multithreading")
    run.add_argument(
        "--max_tests",
        type=int,
        default=10,
        help="Maximum number of tests per sample",
    )
    run.add_argument("--output_file", type=str, default="detailed_results.jsonl", help="Evaluation output filename")
    run.add_argument("--enable_mutation", action="store_true", help="Enable mutation testing during evaluation")
    run.set_defaults(handler=_handle_run)

    eval_parser = subparsers.add_parser("eval", aliases=["evaluate"], help="Run evaluation")
    eval_parser.add_argument("--lang", type=_normalize_runtime_language, required=True, help="Language")
    eval_parser.add_argument("--mode", type=str, default=None, help="Prompt mode")
    eval_parser.add_argument("--model", type=str, default=None, help="Model folder name")
    eval_parser.add_argument("--enable_mutation", action="store_true", help="Enable mutation testing")
    eval_parser.add_argument("--input_file", type=str, default="processed.jsonl", help="Input filename")
    eval_parser.add_argument("--output_file", type=str, default="detailed_results.jsonl", help="Output filename")
    eval_parser.set_defaults(handler=_handle_eval)

    repair = subparsers.add_parser("repair", help="Run iterative repair")
    repair.add_argument("--lang", type=_normalize_runtime_language, required=True, help="Language")
    repair.add_argument("--mode", type=str, default=None, help="Prompt mode")
    repair.add_argument("--model", type=str, default=None, help="Model folder name")
    repair.add_argument("--attempt", type=int, default=1, help="Repair attempt number")
    repair.add_argument("--max_attempts", type=int, default=3, help="Max attempts per sample")
    repair.add_argument("--repair_model", type=str, default="gpt-4", help="Repair model")
    repair.add_argument("--repair_provider", type=str, default="openai", help="Repair provider")
    repair.add_argument("--base_url", type=str, default=None, help="OpenAI-compatible API base URL")
    repair.add_argument("--api_key", type=str, default=None, help="API key")
    repair.add_argument("--input_results", type=str, default=None, help="Explicit input results file")
    repair.add_argument("--concurrency", type=int, default=20, help="Concurrent repair workers")
    repair.add_argument("--delay", type=float, default=0.0, help="Delay between API calls in seconds")
    repair.add_argument("--max_retries", type=int, default=3, help="Maximum number of retry attempts")
    repair.add_argument("--retry_delay", type=float, default=5.0, help="Initial retry delay in seconds")
    repair.set_defaults(handler=_handle_repair)

    repair_preprocess = subparsers.add_parser(
        "repair-preprocess",
        help="Preprocess repair responses for re-evaluation",
    )
    repair_preprocess.add_argument("--input", type=str, default=None, help="Explicit input file path")
    repair_preprocess.add_argument("--output", type=str, default=None, help="Explicit output file path")
    repair_preprocess.add_argument(
        "--lang", type=_normalize_runtime_language, default=None, help="Language"
    )
    repair_preprocess.add_argument("--mode", type=str, default=None, help="Prompt mode")
    repair_preprocess.add_argument("--model", type=str, default=None, help="Model name")
    repair_preprocess.add_argument(
        "--attempt", type=int, default=1, help="Repair attempt number"
    )
    repair_preprocess.add_argument(
        "--quiet", action="store_true", help="Suppress progress messages"
    )
    repair_preprocess.set_defaults(handler=_handle_repair_preprocess)

    agentic = subparsers.add_parser(
        "agentic", help="Run the agentic (headless Claude Code) evaluation mode"
    )
    agentic.add_argument(
        "--lang",
        type=_normalize_runtime_language,
        required=True,
        help="Language (go, rust, ruby, php, julia)",
    )
    agentic.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model for the claude CLI --model flag (omit to use the CLI's own ambient default)",
    )
    agentic.add_argument("--concurrency", type=int, default=4, help="Concurrent agent tasks")
    agentic.add_argument(
        "--timeout", dest="timeout", type=int, default=1800, metavar="SECONDS", help="Wall-clock timeout per batch session"
    )
    agentic.add_argument("--baseline_mode", dest="baseline_mode", type=str, default="standard")
    agentic.add_argument("--baseline_model", dest="baseline_model", type=str, default="claude-sonnet-4-5")
    agentic.add_argument("--output_model_dir", dest="output_model_dir", type=str, default=None)
    agentic.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Only run this repo's selected tasks (validated against task_subset_<lang>.json)",
    )
    agentic.add_argument(
        "--task_id",
        dest="task_id",
        type=str,
        default=None,
        help="Comma-separated explicit task_ids to run (validated against --repo if given)",
    )
    agentic.set_defaults(handler=_handle_agentic)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


def legacy_run_main(argv: Sequence[str] | None = None) -> int:
    command_argv = list(argv) if argv is not None else sys.argv[1:]
    return _run_entrypoint(_ENTRYPOINTS["eval"], command_argv, prog="xrepotest-run")


if __name__ == "__main__":
    raise SystemExit(main())
