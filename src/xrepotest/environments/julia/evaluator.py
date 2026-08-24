"""
Julia-specific evaluator implementation using the BaseEvaluator framework.

Julia evaluation is repository-batched and relies on run_coverage.jl. This
evaluator overrides evaluate_dataset to preserve that workflow while exposing the
same class-based interface as other languages.
"""

import json
import os
from typing import Any, Dict, List, Tuple

from base import BaseEvaluator
from base.metrics import calculate_summary

from .command_utils import parse_coverage_results, run_julia_coverage
from .test_utils import count_function_invocations


class JuliaEvaluator(BaseEvaluator):
    """Julia-specific implementation of test evaluator."""

    def __init__(self):
        super().__init__("julia")
        self.repos_dir = "/app/repo_data"

    def _split_dataset_by_repo(self, dataset: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Dynamically split dataset by repository name extracted from file_path."""
        repo_datasets = {}
        for idx, sample in enumerate(dataset):
            sample["task_id"] = idx
            
            # Extract repo name from file_path (e.g., "DataStructures.jl/src/...)
            file_path = sample.get("file_path", "")
            if "/" in file_path:
                repo_name = file_path.split("/")[0]
            else:
                repo_name = "unknown"
                
            if repo_name not in repo_datasets:
                repo_datasets[repo_name] = []
            repo_datasets[repo_name].append(sample)
            
        return repo_datasets

    def _write_repo_test_file(
        self,
        repo_name: str,
        samples: List[Dict[str, Any]],
        output_dir: str,
    ) -> str:
        os.makedirs(output_dir, exist_ok=True)
        test_file_path = os.path.join(output_dir, f"{repo_name}.jsonl")

        with open(test_file_path, "w", encoding="utf-8") as handle:
            for sample in samples:
                if not sample.get("test"):
                    continue

                function_name = sample.get("function_name", "")
                for test_idx, test_code in enumerate(sample["test"]):
                    test_entry = {
                        "function_name": function_name,
                        "test": test_code,
                        "focal_code": sample.get("focal_code", ""),
                        "start_line": sample.get("function_component", {}).get("start_line", 1),
                        "end_line": sample.get("function_component", {}).get("end_line", 1),
                        "file_path": sample.get("file_path", ""),
                        "test_idx": test_idx,
                    }
                    handle.write(json.dumps(test_entry) + "\n")

        return test_file_path

    def _parse_julia_coverage_results(self, report_file: str) -> List[Dict[str, Any]]:
        coverage_data = parse_coverage_results(report_file)
        return coverage_data.get("results", [])

    def _merge_coverage_results(
        self,
        samples: List[Dict[str, Any]],
        coverage_results: List[Dict[str, Any]],
    ) -> None:
        result_lookup = {}
        for result in coverage_results:
            key = (result.get("function_name", ""), result.get("test_idx", 0))
            result_lookup[key] = result

        for sample in samples:
            function_name = sample.get("function_name", "")
            tests = sample.get("test", [])

            sample["logs"] = []
            sample["checks"] = []
            sample["coverage_stats"] = []

            for test_idx, test_code in enumerate(tests):
                key = (function_name, test_idx)
                invoked = count_function_invocations([test_code], function_name) > 0

                if key in result_lookup:
                    result = result_lookup[key]
                    harness_error = bool(result.get("harness_error", False))
                    test_success = (result.get("pass_rate", 0) == 100.0) and not harness_error

                    check = {
                        "compilation": (
                            not harness_error and
                            result.get("pass", 0)
                            + result.get("fail", 0)
                            + result.get("error", 0)
                            > 0
                        ),
                        "tests": test_success,
                        "coverage": result.get("covered_lines", 0) > 0,
                        "invocation": invoked,
                    }

                    sample["logs"].append(result.get("log", ""))
                    sample["checks"].append(check)
                    sample["coverage_stats"].append(
                        {
                            "covered_lines": result.get("covered_lines", 0),
                            "total_lines": result.get("total_lines", 0),
                        }
                    )
                else:
                    sample["logs"].append("No coverage result found")
                    sample["checks"].append(
                        {
                            "compilation": False,
                            "tests": False,
                            "coverage": False,
                            "invocation": invoked,
                        }
                    )
                    sample["coverage_stats"].append(None)

    def evaluate_dataset(
        self,
        dataset: List[Dict[str, Any]],
        **kwargs
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        repo_datasets = self._split_dataset_by_repo(dataset)

        test_dir = "/tmp/tests"
        report_dir = "/tmp/reports"
        os.makedirs(test_dir, exist_ok=True)
        os.makedirs(report_dir, exist_ok=True)

        all_results = []
        for repo_name, samples in repo_datasets.items():
            if not samples:
                continue

            test_file = self._write_repo_test_file(repo_name, samples, test_dir)

            repo_path = os.path.join(self.repos_dir, repo_name)
            if os.path.isdir(repo_path):
                success, log = run_julia_coverage(repo_path, test_file, report_dir)
                if not success:
                    print(f"Warning: Coverage failed for {repo_name}")

            report_file = os.path.join(report_dir, f"{repo_name}.jsonl")
            coverage_results = self._parse_julia_coverage_results(report_file)
            self._merge_coverage_results(
                samples,
                coverage_results,
            )
            all_results.extend(samples)

        summary = calculate_summary(all_results)
        return all_results, summary

    def create_test_file(
        self,
        file_path: str,
        sample: Dict[str, Any],
        test_code: str,
    ) -> str:
        return self.get_focal_file_path(sample)

    def check_compilation(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
        test_code: str,
    ) -> Tuple[bool, str]:
        return True, "Julia compilation is checked during batch coverage run"

    def run_tests(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
        test_code: str,
    ) -> Tuple[bool, str]:
        return True, "Julia tests run in batch via run_coverage.jl"

    def generate_coverage(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
        test_code: str,
    ) -> Tuple[bool, Any]:
        return False, "Julia coverage is generated in evaluate_dataset batch mode"

    def check_invocation(self, test_code: str, function_name: str) -> bool:
        return count_function_invocations([test_code], function_name) > 0
