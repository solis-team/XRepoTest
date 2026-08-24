"""Helper utilities for the error classification CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


from experiments.evaluation.common.constants import SUPPORTED_LANGUAGES as _SUPPORTED_LANGUAGES

SUPPORTED_LANGUAGES = list(_SUPPORTED_LANGUAGES)


@dataclass(frozen=True)
class ClassificationTarget:
    """One classification target resolved from CLI input."""

    input_file: Path
    output_dir: Path
    language: str
    mode: str | None = None
    model: str | None = None

    @property
    def error_analysis_path(self) -> Path:
        return self.output_dir / "error_analysis.jsonl"

    @property
    def api_breakdown_path(self) -> Path:
        return self.output_dir / "api_hallucination_breakdown.json"


def parse_csv_values(raw_value: str | None) -> list[str]:
    """Parse comma-separated values into normalized non-empty tokens."""
    if not raw_value:
        return []
    return [token.strip() for token in raw_value.split(",") if token.strip()]


def combine_filter_values(single_value: str | None, csv_values: str | None) -> list[str]:
    """Combine single and comma-separated filters into an ordered unique list."""
    combined: list[str] = []
    if csv_values:
        combined.extend(parse_csv_values(csv_values))
    if single_value:
        value = single_value.strip()
        if value:
            combined.append(value)

    unique: list[str] = []
    for value in combined:
        if value not in unique:
            unique.append(value)
    return unique


def infer_mode_model_from_path(input_file: Path, language: str) -> tuple[str | None, str | None]:
    """
    Infer mode/model from common evaluation path shapes.

    Expected common layout:
      .../{language}/{mode}/{model}/detailed_results.jsonl
    """
    language = language.strip()
    parts = input_file.parts

    # Prefer the language segment closest to the file to avoid false matches
    # from unrelated ancestors (e.g., /home/user/go/.../results/go/...).
    for idx in range(len(parts) - 3, -1, -1):
        if parts[idx] == language:
            return parts[idx + 1], parts[idx + 2]

    return None, None


def build_single_file_target(
    *,
    input_file: Path,
    language: str,
    output_dir: Path | None,
    mode_filters: list[str],
    model_filters: list[str],
) -> ClassificationTarget:
    """Build and validate one target from --input_file."""
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    inferred_mode, inferred_model = infer_mode_model_from_path(input_file, language)
    mode = _resolve_single_file_metadata("mode", inferred_mode, mode_filters)
    model = _resolve_single_file_metadata("model", inferred_model, model_filters)

    resolved_output_dir = output_dir if output_dir is not None else input_file.parent

    return ClassificationTarget(
        input_file=input_file,
        output_dir=resolved_output_dir,
        language=language,
        mode=mode,
        model=model,
    )


def discover_directory_targets(
    *,
    input_dir: Path,
    language: str,
    output_base_dir: Path | None,
    mode_filters: list[str],
    model_filters: list[str],
) -> list[ClassificationTarget]:
    """Discover and filter detailed_results targets from an input directory."""
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    targets: list[ClassificationTarget] = []
    scan_root = input_dir / language if (input_dir / language).is_dir() else input_dir

    for result_file in sorted(scan_root.rglob("detailed_results.jsonl")):
        inferred_mode, inferred_model = infer_mode_model_from_path(result_file, language)

        if mode_filters and (inferred_mode is None or inferred_mode not in mode_filters):
            continue
        if model_filters and (inferred_model is None or inferred_model not in model_filters):
            continue

        if output_base_dir is None:
            resolved_output_dir = result_file.parent
        else:
            relative_parent = result_file.parent.relative_to(input_dir)
            resolved_output_dir = output_base_dir / relative_parent

        targets.append(
            ClassificationTarget(
                input_file=result_file,
                output_dir=resolved_output_dir,
                language=language,
                mode=inferred_mode,
                model=inferred_model,
            )
        )

    return targets


def _resolve_single_file_metadata(
    metadata_name: str, inferred_value: str | None, selected_values: list[str]
) -> str | None:
    """Resolve mode/model metadata for a single input file."""
    if not selected_values:
        return inferred_value

    if len(selected_values) > 1:
        raise ValueError(
            f"Multiple {metadata_name} values were provided for a single input file: "
            f"{', '.join(selected_values)}"
        )

    selected_value = selected_values[0]
    if inferred_value is not None and inferred_value != selected_value:
        raise ValueError(
            f"Provided {metadata_name} '{selected_value}' does not match inferred "
            f"{metadata_name} '{inferred_value}' from path: {inferred_value}"
        )

    return selected_value
