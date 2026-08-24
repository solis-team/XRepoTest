"""
Iterative Repair Module for xrepotest Test Generation

This module provides feedback-based iterative repair capabilities for LLM-generated
unit tests. When tests fail, the system sends error messages back to the LLM
for repair, with configurable repair attempts.

Main components:
- engine: Core orchestration logic for repair workflow
- prompt_builder: Language-agnostic repair prompt construction
"""

from experiments.evaluation.repair.engine import RepairEngine
from experiments.evaluation.repair.prompt_builder import PromptBuilder

__all__ = [
    'RepairEngine',
    'PromptBuilder',
]
