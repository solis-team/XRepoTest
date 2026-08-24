"""
Processing Modules

Batch processing and pipeline orchestration for error classification.
"""

from experiments.analysis.error_analysis.processors.batch import BatchErrorClassifier, process_directory

__all__ = [
    'BatchErrorClassifier',
    'process_directory',
]
