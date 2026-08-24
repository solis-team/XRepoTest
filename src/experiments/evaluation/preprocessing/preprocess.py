import argparse
import json
import sys
from pathlib import Path

from experiments.evaluation.preprocessing.preprocess_utils import (
    derive_default_output_path,
    preprocess_file_to_output,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract test code from LLM responses")
    parser.add_argument(
        "--input_directory",
        type=str,
        required=True,
        help="Input JSONL file path",
    )
    parser.add_argument(
        "--output_directory",
        type=str,
        default="",
        help="Output JSONL file path (default: derived under results/)",
    )
    parser.add_argument(
        "--max_tests",
        type=int,
        default=10,
        help="Maximum number of test blocks per sample (default: 10)",
    )

    args = parser.parse_args()
    input_path = Path(args.input_directory)

    if args.output_directory:
        output_path = Path(args.output_directory)
    else:
        output_path = derive_default_output_path(input_path)

    print(f"Reading from {input_path}...")
    print(f"Writing to {output_path}...")

    try:
        processed = preprocess_file_to_output(
            input_path=input_path,
            output_path=output_path,
            max_tests=args.max_tests,
            drop_prompt=True,
        )
    except FileNotFoundError:
        print(f"Error: Input file '{input_path}' not found")
        return 1
    except json.JSONDecodeError as exc:
        print(f"Error: Invalid JSON in input file - {exc}")
        return 1
    except Exception as exc:
        print(f"Error processing file: {exc}")
        return 1

    print(f"[OK] Successfully processed {len(processed)} samples")
    print(f"[OK] Output saved to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
