"""Language-specific configurations and utilities for xrepotest."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageConfig:
    """Configuration for a specific programming language environment."""

    name: str
    file_extension: str
    test_framework: str
    mutation_tool: str | None
    dataset_name: str


LANGUAGE_CONFIGS: dict[str, LanguageConfig] = {
    "go": LanguageConfig(
        name="go",
        file_extension=".go",
        test_framework="testing",
        mutation_tool="go-mutesting",
        dataset_name="go",
    ),
    "rust": LanguageConfig(
        name="rust",
        file_extension=".rs",
        test_framework="cargo test",
        mutation_tool="cargo-mutants",
        dataset_name="rust",
    ),
    "julia": LanguageConfig(
        name="julia",
        file_extension=".jl",
        test_framework="Test",
        mutation_tool=None,
        dataset_name="julia",
    ),
    "php": LanguageConfig(
        name="php",
        file_extension=".php",
        test_framework="PHPUnit",
        mutation_tool="infection",
        dataset_name="php",
    ),
    "ruby": LanguageConfig(
        name="ruby",
        file_extension=".rb",
        test_framework="RSpec",
        mutation_tool="mutant",
        dataset_name="ruby",
    ),
}

SUPPORTED_LANGUAGES: tuple[str, ...] = tuple(LANGUAGE_CONFIGS.keys())
MUTATION_SUPPORTED_LANGS = frozenset(
    language for language, config in LANGUAGE_CONFIGS.items() if config.mutation_tool
)
EVAL_MUTATION_SUPPORTED_LANGS = frozenset({"rust", "go", "ruby"})


def normalize_language(language: str) -> str:
    """Normalize a language identifier to lowercase and validate support."""
    normalized = language.strip().lower()
    if normalized not in LANGUAGE_CONFIGS:
        raise ValueError(
            f"Unsupported language: {language}. "
            f"Supported languages: {', '.join(SUPPORTED_LANGUAGES)}"
        )
    return normalized


def get_language_config(language: str) -> LanguageConfig:
    """Get configuration for a specific language."""
    return LANGUAGE_CONFIGS[normalize_language(language)]


def get_supported_languages() -> list[str]:
    """Get list of all supported language identifiers."""
    return list(SUPPORTED_LANGUAGES)


def has_mutation_support(language: str) -> bool:
    """Check if a language has mutation testing support."""
    return normalize_language(language) in MUTATION_SUPPORTED_LANGS


__all__ = [
    "LANGUAGE_CONFIGS",
    "SUPPORTED_LANGUAGES",
    "MUTATION_SUPPORTED_LANGS",
    "EVAL_MUTATION_SUPPORTED_LANGS",
    "LanguageConfig",
    "normalize_language",
    "get_language_config",
    "get_supported_languages",
    "has_mutation_support",
]
