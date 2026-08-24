"""Shared constants for evaluation pipelines."""

from __future__ import annotations

from xrepotest.languages import (
    EVAL_MUTATION_SUPPORTED_LANGS,
    SUPPORTED_LANGUAGES as _SUPPORTED_LANGUAGES,
)

LANGUAGE_DOCKER_IMAGES: dict[str, str] = {
    "go": "dungxg502/xrepotest-go:latest",
    "rust": "dungxg502/xrepotest-rust:latest",
    "julia": "dungxg502/xrepotest-julia:latest",
    "php": "dungxg502/xrepotest-php:latest",
    "ruby": "dungxg502/xrepotest-ruby:latest",
}

# Languages that support mutation testing in the primary Docker evaluator.
MUTATION_SUPPORTED_LANGS = EVAL_MUTATION_SUPPORTED_LANGS
SUPPORTED_LANGUAGES = _SUPPORTED_LANGUAGES
