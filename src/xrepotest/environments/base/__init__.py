"""
Base package for shared evaluation functionality across all language environments.

This package contains common code used by Go, Rust, Julia, PHP, and Ruby evaluators
to eliminate duplication and ensure consistency.
"""

from .metrics import calculate_summary
from .evaluator import BaseEvaluator

__all__ = ['calculate_summary', 'BaseEvaluator']
