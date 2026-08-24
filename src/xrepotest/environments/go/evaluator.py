"""
Go-specific evaluator implementation using the BaseEvaluator framework.
"""

import os
from typing import Any, Dict, Tuple

from base import BaseEvaluator

from .command_utils import (
    check_compilation,
    check_test,
    generate_coverage_report,
    run_mutation_score,
)
from .test_utils import create_go_file, is_invoke_in_code


class GoEvaluator(BaseEvaluator):
    """Go-specific implementation of test evaluator."""

    def __init__(self):
        super().__init__("go")

    def create_test_file(
        self,
        file_path: str,
        sample: Dict[str, Any],
        test_code: str,
    ) -> str:
        return create_go_file(file_path, sample["function_name"], test_code)

    def check_compilation(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
        test_code: str,
    ) -> Tuple[bool, str]:
        compilation_success, compile_log = check_compilation(test_file_path, test_code)
        if (
            not compilation_success
            or "build failed" in compile_log
            or "setup failed" in compile_log
        ):
            return False, compile_log
        return True, compile_log

    def run_tests(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
        test_code: str,
    ) -> Tuple[bool, str]:
        return check_test(test_file_path, test_code)

    def generate_coverage(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
        test_code: str,
    ) -> Tuple[bool, Any]:
        focal_file_path = self.get_focal_file_path(sample)
        success, coverage_log = generate_coverage_report(
            test_file_path,
            test_code,
            focal_file_path,
            sample["function_component"]["start_line"],
            sample["function_component"]["end_line"],
        )
        if success and isinstance(coverage_log, dict):
            return True, coverage_log
        return False, None

    def check_invocation(self, test_code: str, function_name: str) -> bool:
        return is_invoke_in_code(test_code, function_name)

    def run_mutation_testing(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
    ) -> Tuple[bool, Dict[str, Any]]:
        focal_file_path = self.get_focal_file_path(sample)
        return run_mutation_score(
            focal_file_path=focal_file_path,
            focal_function_name=sample["function_name"],
            timeout=300,
        )
