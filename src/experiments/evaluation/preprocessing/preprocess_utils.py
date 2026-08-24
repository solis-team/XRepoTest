"""Shared preprocessing utilities for extracting test code from LLM responses."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from experiments.evaluation.common.task_ids import normalize_task_id


def _strip_php_docblock(code: str) -> str:
    """Strip file-header docblock between declare() and namespace in PHP code.

    PHP forbids any non-whitespace content between ``declare(strict_types=1);``
    and ``namespace Foo;``. The agent often inserts a ``/** ... */`` file-header
    docblock there, which causes a fatal compile error.
    """
    lines = code.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # After declare(strict_types=1); skip empty lines and comments
        # (//, /* */, /** */) before namespace — PHP forbids anything there.
        if re.match(r"^\s*declare\s*\(\s*strict_types\s*=\s*1\s*\)\s*;", line):
            out.append(line)
            i += 1
            while i < len(lines) and (
                lines[i].strip() == ""
                or lines[i].strip().startswith("//")
                or lines[i].strip().startswith("/*")
                or lines[i].strip().startswith("*")
                or lines[i].strip() == "*/"
            ):
                i += 1
            continue

        out.append(line)
        i += 1

    return "\n".join(out)


def extract_code_from_markdown(text: str) -> str:
    """Extract code from closed markdown code fences only.

    Supported language tags are: ``julia``, ``ruby``, ``go``, ``rust``, ``php``.
    If no matching closed fence is found, an empty string is returned.
    """
    code_block_pattern = r'```(?:julia|ruby|go|rust|php)?\r?\n(.*?)```'
    matches = re.findall(code_block_pattern, text, re.DOTALL)

    if matches:
        code = '\n\n'.join(matches)
        # Clean PHP code: strip docblock between declare() and namespace
        if code.lstrip().startswith("<?php"):
            code = _strip_php_docblock(code)
        return code
    return ''


def process_responses(raw_responses: list[str], max_tests: int = 10) -> list[str]:
    """Process raw LLM responses and extract test code.

    Args:
        raw_responses: List of raw responses from LLM
        max_tests: Maximum number of test blocks to return

    Returns:
        List of extracted test code blocks
    """
    all_test_code: list[str] = []

    for raw_response in raw_responses:
        code = extract_code_from_markdown(raw_response)
        if code.strip():
            all_test_code.append(code)

    if len(all_test_code) > max_tests:
        all_test_code = all_test_code[:max_tests]

    # Fallback: if no code blocks were found, use the raw response so the
    # sample is not dropped; evaluation will report a compilation error.
    if not all_test_code and raw_responses:
        all_test_code = raw_responses[:max_tests]

    return all_test_code


def normalize_response_payload(response: Any) -> list[str]:
    """Normalize response payload to list[str]."""
    if response is None:
        return []
    if isinstance(response, str):
        return [response]
    if isinstance(response, list):
        return [item if isinstance(item, str) else str(item) for item in response]
    return [str(response)]


def replace_path_segment(path: Path, source: str, target: str) -> Path:
    """Replace an exact path segment while preserving the rest of the path."""
    parts = list(path.parts)
    if source not in parts:
        raise ValueError(f"Segment '{source}' not found in path: {path}")
    idx = parts.index(source)
    parts[idx] = target
    return Path(*parts)


def transform_filename(
    filename: str,
    replacements: Iterable[tuple[str, str]],
    fallback: str | None = None,
) -> str:
    """Apply ordered substring replacements to a file name."""
    transformed = filename
    for old, new in replacements:
        transformed = transformed.replace(old, new)
    if fallback is not None and transformed == filename:
        return fallback
    return transformed


def derive_default_output_path(
    input_path: Path,
    *,
    source_segment: str = "responses",
    target_segment: str = "results",
    filename_replacements: Iterable[tuple[str, str]] = (
        ("prompts_responses", "processed"),
        ("responses", "processed"),
    ),
    fallback_filename: str = "processed_response.jsonl",
) -> Path:
    """Derive output path from a source file using segment-safe path replacement."""
    output_name = transform_filename(
        input_path.name,
        replacements=filename_replacements,
        fallback=fallback_filename,
    )
    if source_segment in input_path.parts:
        mapped_path = replace_path_segment(input_path, source_segment, target_segment)
        return mapped_path.with_name(output_name)
    return input_path.parent / output_name


def load_jsonl(input_path: Path) -> list[dict[str, Any]]:
    """Load a JSONL file into a list of dicts."""
    records: list[dict[str, Any]] = []
    with open(input_path, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def write_jsonl(output_path: Path, records: Iterable[dict[str, Any]]) -> None:
    """Write iterable records to JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def preprocess_response_records(
    records: list[dict[str, Any]],
    *,
    max_tests: int = 10,
    drop_prompt: bool = True,
) -> list[dict[str, Any]]:
    """Normalize and preprocess response payloads for evaluation."""
    processed: list[dict[str, Any]] = []
    for sample in records:
        normalized = dict(sample)
        normalized["task_id"] = normalize_task_id(normalized.get("task_id"))
        raw_responses = normalize_response_payload(normalized.get("response"))
        normalized["response"] = process_responses(raw_responses, max_tests=max_tests)
        if drop_prompt:
            normalized.pop("prompt", None)
        processed.append(normalized)
    return processed


def preprocess_file_to_output(
    input_path: Path,
    output_path: Path,
    *,
    max_tests: int = 10,
    drop_prompt: bool = True,
) -> list[dict[str, Any]]:
    """Load, preprocess, and write a JSONL response file."""
    records = load_jsonl(input_path)
    processed = preprocess_response_records(
        records,
        max_tests=max_tests,
        drop_prompt=drop_prompt,
    )
    write_jsonl(output_path, processed)
    return processed
