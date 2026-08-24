"""
PHP-specific evaluator implementation using the BaseEvaluator framework.
"""

import os
from typing import Any, Dict, Tuple

from base import BaseEvaluator

from .command_utils import check_compilation, check_test, generate_coverage_report
from .mutation_utils import run_mutation_testing
from .test_utils import create_php_file, is_invoke_in_code


class PHPEvaluator(BaseEvaluator):
    """PHP-specific implementation of test evaluator."""

    def __init__(self):
        super().__init__("php")

    def create_test_file(
        self,
        file_path: str,
        sample: Dict[str, Any],
        test_code: str,
    ) -> str:
        focal_file_path = self.get_focal_file_path(sample)
        return create_php_file(focal_file_path, sample["function_name"], test_code)

    def check_compilation(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
        test_code: str,
    ) -> Tuple[bool, str]:
        return check_compilation(test_file_path, test_code)

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
        success, coverage_stats = generate_coverage_report(
            test_file_path,
            test_code,
            focal_file_path,
            sample["function_component"]["start_line"],
            sample["function_component"]["end_line"],
        )
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
        focal_file_path = self.get_focal_file_path(sample)
        # Extract repo name for project root
        repo_name = sample["file_path"].split("/")[0]
        project_root = os.path.abspath(os.path.join("repo_data", repo_name))
        
        return run_mutation_testing(
            test_file_path=test_file_path,
            focal_file_path=focal_file_path,
            focal_function_name=sample["function_name"],
            project_root=project_root,
            timeout=900,
            focal_start_line=sample.get("function_component", {}).get("start_line"),
            focal_end_line=sample.get("function_component", {}).get("end_line"),
        )
