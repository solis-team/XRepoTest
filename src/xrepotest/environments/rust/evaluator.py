"""
Rust-specific evaluator implementation using the BaseEvaluator framework.
"""

from typing import Any, Dict, Tuple

from base import BaseEvaluator

from .command_utils import (
    check_compilation,
    check_test,
    generate_coverage_report,
    run_mutation_score,
)
from .test_utils import create_rust_file, is_invoke_in_code, return_file


class RustEvaluator(BaseEvaluator):
    """Rust-specific implementation of test evaluator."""

    def __init__(self):
        super().__init__("rust")

    def _evaluate_sample(
        self,
        sample: Dict[str, Any],
        enable_mutation_testing: bool,
    ) -> None:
        file_path = self.get_focal_file_path(sample)
        original_code = sample["file_content"]
        try:
            super()._evaluate_sample(sample, enable_mutation_testing)
        finally:
            return_file(file_path, original_code)

    def create_test_file(
        self,
        file_path: str,
        sample: Dict[str, Any],
        test_code: str,
    ) -> str:
        focal_file_path = self.get_focal_file_path(sample)
        create_rust_file(
            focal_file_path,
            sample["file_content"],
            test_code,
        )
        return focal_file_path

    def check_compilation(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
        test_code: str,
    ) -> Tuple[bool, str]:
        test_name = "test_" + sample["function_name"]
        return check_compilation(test_file_path, test_name)

    def run_tests(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
        test_code: str,
    ) -> Tuple[bool, str]:
        test_name = "test_" + sample["function_name"]
        return check_test(test_file_path, test_name)

    def generate_coverage(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
        test_code: str,
    ) -> Tuple[bool, Any]:
        test_name = "test_" + sample["function_name"]
        success, coverage_stats = generate_coverage_report(test_file_path, test_name, sample)
        if success and isinstance(coverage_stats, dict):
            return True, coverage_stats
        return False, None

    def check_invocation(self, test_code: str, function_name: str) -> bool:
        return is_invoke_in_code(test_code, function_name)

    def run_mutation_testing(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
    ) -> Tuple[bool, Dict[str, Any]]:
        return run_mutation_score(
            focal_file_path=self.get_focal_file_path(sample),
            focal_function_name=sample["function_name"],
            timeout=900,
        )
