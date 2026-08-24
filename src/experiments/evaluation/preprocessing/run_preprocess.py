"""
Run preprocessing over all matching response JSONL files in a directory tree.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from experiments.evaluation.preprocessing.preprocess_utils import (
    preprocess_file_to_output,
    replace_path_segment,
    transform_filename,
)


def _derive_output_base(input_dir: Path, explicit_output: str | None) -> Path:
    if explicit_output:
        return Path(explicit_output).resolve()
    try:
        return replace_path_segment(input_dir, "responses", "results")
    except ValueError:
        return input_dir.parent / "results"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Process all JSONL files in a folder with preprocess.py"
    )
    parser.add_argument(
        "input_folder",
        type=str,
        help="Path to folder containing JSONL files to process",
        default="responses",
    )
    parser.add_argument(
        "--output_folder",
        type=str,
        default=None,
        help="Path to output folder (default: segment-safe responses -> results mapping)",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*responses.jsonl",
        help="File pattern to match (default: *responses.jsonl)",
    )
    parser.add_argument(
        "--max_tests",
        type=int,
        default=10,
        help="Maximum number of test blocks per sample (default: 10)",
    )

    args = parser.parse_args()
    input_dir = Path(args.input_folder).resolve()

    if not input_dir.exists():
        print(f"❌ Directory not found: {input_dir}")
        return 1

    response_files = list(input_dir.rglob(args.pattern))
    if not response_files:
        print(f"❌ No files matching '{args.pattern}' found in: {input_dir}")
        return 1

    output_base = _derive_output_base(input_dir, args.output_folder)

    print(f"\n{'='*80}")
    print(f"Processing folder: {input_dir}")
    print(f"Found {len(response_files)} file(s) matching '{args.pattern}'")
    print(f"{'='*80}")

    failed_count = 0
    success_count = 0

    for input_file in response_files:
        relative_path = input_file.relative_to(input_dir)
        output_filename = transform_filename(
            f"{relative_path.stem}.jsonl",
            replacements=(
                ("prompts_responses", "processed"),
                ("responses", "processed"),
            ),
            fallback=f"{relative_path.stem}.jsonl",
        )
        output_dir = output_base / relative_path.parent
        output_file = output_dir / output_filename
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n📄 Processing: {relative_path}")
        print(f"   Output: {output_file.relative_to(output_base)}")

        if output_file.exists():
            print("   ⏭️  Skipped: Output file already exists")
            continue

        try:
            preprocess_file_to_output(
                input_path=input_file,
                output_path=output_file,
                max_tests=args.max_tests,
                drop_prompt=True,
            )
            print(f"   ✅ Success: {output_file.name}")
            success_count += 1
        except Exception as exc:
            print(f"   ❌ Error processing {input_file.name}: {exc}")
            failed_count += 1

    print(f"\n{'='*80}")
    print(f"✅ Processing complete. Successful: {success_count}, Failed: {failed_count}")
    print(f"{'='*80}\n")
    return 1 if failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
