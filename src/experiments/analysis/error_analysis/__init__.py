"""
Error Classification Package for LLM-Generated Unit Tests

This package provides automated error classification for test code generated
by Large Language Models across multiple programming languages (Rust, Go, Julia, PHP, Ruby).
"""

from experiments.analysis.error_analysis.classifiers.base import (
    ClassificationResult,
    ErrorCategory,
    ErrorClassifier,
    ErrorDetails,
)
from experiments.analysis.error_analysis.classifiers import (
    GoErrorClassifier,
    JuliaErrorClassifier,
    PHPErrorClassifier,
    RubyErrorClassifier,
    RustErrorClassifier,
)
from experiments.analysis.error_analysis.processors import BatchErrorClassifier, process_directory

__version__ = '1.0.0'

__all__ = [
    'ErrorCategory',
    'ErrorDetails',
    'ClassificationResult',
    'ErrorClassifier',
    'RustErrorClassifier',
    'GoErrorClassifier',
    'JuliaErrorClassifier',
    'PHPErrorClassifier',
    'RubyErrorClassifier',
    'BatchErrorClassifier',
    'process_directory',
]
