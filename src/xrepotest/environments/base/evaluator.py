"""
Base evaluator classes for language-specific test evaluation.

This module provides abstract base classes that encapsulate the common evaluation
logic shared across all language environments (Go, Rust, Julia, PHP, Ruby).
Language-specific implementations inherit from these bases and override only
the parts that differ between languages.
"""

import os
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Tuple
from xrepotest.languages import get_language_config, LanguageConfig
from .metrics import calculate_summary


class BaseEvaluator(ABC):
    """
    Abstract base class for language-specific test evaluators.
    
    This class implements the common evaluation flow:
    1. Initialize samples with empty test results
    2. Filter to samples with generated tests
    3. For each test: compile, run, measure coverage, optionally run mutation
    4. Calculate summary metrics
    
    Subclasses must implement language-specific methods for:
    - Creating test files
    - Checking compilation
    - Running tests
    - Generating coverage reports
    - Running mutation testing (if supported)
    """
    
    def __init__(self, language: str):
        """
        Initialize the evaluator.
        
        Args:
            language: Programming language identifier (go, rust, julia, php, ruby)
        """
        self.config: LanguageConfig = get_language_config(language)
        self.language = language

    def get_focal_file_path(self, sample: Dict[str, Any]) -> str:
        """
        Get the absolute path to the focal source file.
        
        Args:
            sample: Sample dictionary containing file_path
            
        Returns:
            String path to the focal file
        """
        return os.path.abspath(os.path.join("repo_data", sample["file_path"]))
    
    def evaluate_dataset(
        self,
        dataset: List[Dict[str, Any]],
        enable_mutation_testing: bool = False
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Evaluate a dataset of test generation samples.
        
        Args:
            dataset: List of samples, each containing:
                - function_name: Name of the function being tested
                - file_path: Path to the source file
                - file_content: Full source file content
                - test: List of generated test code strings
                - function_component: Dict with start_line, end_line
                - metadata: Additional metadata
            enable_mutation_testing: Whether to run mutation testing on passed tests
        
        Returns:
            Tuple of (evaluated_dataset, summary_metrics)
        """
        # Initialize all samples with empty result fields
        for sample in dataset:
            sample["logs"] = []
            sample["checks"] = []
            sample["coverage_stats"] = []
            if enable_mutation_testing:
                sample["mutation_scores"] = []
        
        # Filter to samples with generated tests
        filtered_dataset = [s for s in dataset if s.get("test")]
        
        # Evaluate each sample
        for i, sample in enumerate(filtered_dataset):
            print(f"Evaluate sample {i + 1}/{len(filtered_dataset)}...")
            self._evaluate_sample(sample, enable_mutation_testing)
        
        # Calculate summary metrics
        summary = calculate_summary(dataset)
        
        return dataset, summary
    
    def _evaluate_sample(
        self,
        sample: Dict[str, Any],
        enable_mutation_testing: bool
    ) -> None:
        """
        Evaluate all test responses for a single sample.
        
        Args:
            sample: Sample dictionary to evaluate (modified in-place)
            enable_mutation_testing: Whether to run mutation testing
        """
        file_path = self.get_focal_file_path(sample)
        
        # Evaluate each test response
        for test_idx, test_code in enumerate(sample["test"]):
            result = self._initialize_result()
            try:
                self._evaluate_test_response(
                    sample=sample,
                    test_code=test_code,
                    test_idx=test_idx,
                    file_path=file_path,
                    enable_mutation_testing=enable_mutation_testing,
                    result=result,
                )
            except Exception as e:
                print(f"  Error evaluating test {test_idx + 1}: {e}")
                result["log"] = f"Evaluation error: {str(e)}"

            self._append_result(sample, result, enable_mutation_testing)

    @staticmethod
    def _initialize_result() -> Dict[str, Any]:
        """Create a result container for a single test response."""
        return {
            "log": None,
            "check": {
                "compilation": False,
                "tests": False,
                "coverage": None,
                "invocation": False,
            },
            "coverage_stats": None,
            "mutation_result": None,
        }

    def _append_result(
        self,
        sample: Dict[str, Any],
        result: Dict[str, Any],
        enable_mutation_testing: bool,
    ) -> None:
        """Append one test response result to sample-level arrays."""
        sample["logs"].append(result["log"])
        sample["checks"].append(result["check"])
        sample["coverage_stats"].append(result["coverage_stats"])
        if enable_mutation_testing:
            sample["mutation_scores"].append(result["mutation_result"])

    def _evaluate_test_response(
        self,
        sample: Dict[str, Any],
        test_code: str,
        test_idx: int,
        file_path: str,
        enable_mutation_testing: bool,
        result: Dict[str, Any],
    ) -> None:
        """
        Evaluate a single test response and mutate result in-place.
        """
        test_file_path, compilation_success = self._run_compilation_phase(
            file_path=file_path,
            sample=sample,
            test_code=test_code,
            result=result,
        )

        if not compilation_success:
            return

        test_success = self._run_test_phase(
            test_file_path=test_file_path,
            sample=sample,
            test_code=test_code,
            result=result,
        )

        self._run_coverage_phase(
            test_file_path=test_file_path,
            sample=sample,
            test_code=test_code,
            result=result,
        )

        if enable_mutation_testing and test_success:
            self._run_mutation_phase(
                test_idx=test_idx,
                test_file_path=test_file_path,
                sample=sample,
                result=result,
            )

    def _run_compilation_phase(
        self,
        file_path: str,
        sample: Dict[str, Any],
        test_code: str,
        result: Dict[str, Any],
    ) -> Tuple[str, bool]:
        """Create test file and evaluate compilation."""
        test_file_path = self.create_test_file(
            file_path=file_path,
            sample=sample,
            test_code=test_code,
        )
        
        # Check invocation regardless of compilation success
        result["check"]["invocation"] = self.check_invocation(
            test_code=test_code,
            function_name=sample["function_name"],
        )
        
        compilation_success, compile_log = self.check_compilation(
            test_file_path=test_file_path,
            sample=sample,
            test_code=test_code,
        )
        if not compilation_success:
            result["log"] = compile_log
            return test_file_path, False

        result["check"]["compilation"] = True
        return test_file_path, True

    def _run_test_phase(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
        test_code: str,
        result: Dict[str, Any],
    ) -> bool:
        """
        Run tests and update result with pass/fail state.
        
        Args:
            test_file_path: Path to the generated test file
            sample: Sample dictionary
            test_code: Test code string
            result: Result container to update
            
        Returns:
            True if all tests passed, False otherwise
        """
        test_success, test_log = self.run_tests(
            test_file_path=test_file_path,
            sample=sample,
            test_code=test_code,
        )
        result["log"] = test_log
        if test_success:
            result["check"]["tests"] = True
        return test_success

    def _run_coverage_phase(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
        test_code: str,
        result: Dict[str, Any],
    ) -> None:
        """
        Generate coverage and store result details.
        
        Args:
            test_file_path: Path to the generated test file
            sample: Sample dictionary
            test_code: Test code string
            result: Result container to update
        """
        coverage_success, coverage_stats = self.generate_coverage(
            test_file_path=test_file_path,
            sample=sample,
            test_code=test_code,
        )
        if coverage_success and isinstance(coverage_stats, dict):
            result["check"]["coverage"] = True
        result["coverage_stats"] = coverage_stats

    def _run_mutation_phase(
        self,
        test_idx: int,
        test_file_path: str,
        sample: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        """Run mutation testing for a passing test response."""
        print(f"  Running mutation testing for test {test_idx + 1}...")
        mutation_success, mutation_data = self.run_mutation_testing(
            test_file_path=test_file_path,
            sample=sample,
        )
        if mutation_success:
            result["check"]["mutation"] = True
            result["mutation_result"] = mutation_data
            print(f"    Mutation score: {mutation_data['mutation_score']:.2%} "
                  f"({mutation_data['killed_count']}/{mutation_data['total_count']})")
        else:
            result["check"]["mutation"] = False
            result["mutation_result"] = mutation_data
            print(f"    Mutation testing failed: {mutation_data.get('error_message', 'Unknown error')}")
    
    # Abstract methods that subclasses must implement
    
    @abstractmethod
    def create_test_file(
        self,
        file_path: str,
        sample: Dict[str, Any],
        test_code: str
    ) -> str:
        """
        Create a test file with the given test code.
        
        Args:
            file_path: Path to the source file being tested
            sample: Sample data dictionary
            test_code: Generated test code
        
        Returns:
            Path to the created test file
        """
        pass
    
    @abstractmethod
    def check_compilation(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
        test_code: str
    ) -> Tuple[bool, str]:
        """
        Check if the test code compiles.
        
        Args:
            test_file_path: Path to the test file
            sample: Sample data dictionary
            test_code: Test code string
        
        Returns:
            Tuple of (success: bool, log: str)
        """
        pass
    
    @abstractmethod
    def run_tests(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
        test_code: str
    ) -> Tuple[bool, str]:
        """
        Run the tests and return results.
        
        Args:
            test_file_path: Path to the test file
            sample: Sample data dictionary
            test_code: Test code string
        
        Returns:
            Tuple of (success: bool, log: str)
        """
        pass
    
    @abstractmethod
    def generate_coverage(
        self,
        test_file_path: str,
        sample: Dict[str, Any],
        test_code: str
    ) -> Tuple[bool, Any]:
        """
        Generate coverage report for the test.
        
        Args:
            test_file_path: Path to the test file
            sample: Sample data dictionary
            test_code: Test code string
        
        Returns:
            Tuple of (success: bool, coverage_data: dict or str)
            Coverage data should be a dict with 'covered_lines' and 'total_lines' on success
        """
        pass
    
    @abstractmethod
    def check_invocation(
        self,
        test_code: str,
        function_name: str
    ) -> bool:
        """
        Check if test code invokes the focal function.
        
        Args:
            test_code: Test code string
            function_name: Name of the function being tested
        
        Returns:
            True if function is invoked, False otherwise
        """
        pass
    
    def run_mutation_testing(
        self,
        test_file_path: str,
        sample: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Run mutation testing (optional, override if supported).
        
        Args:
            test_file_path: Path to the test file
            sample: Sample data dictionary
        
        Returns:
            Tuple of (success: bool, mutation_data: dict)
            mutation_data should contain: killed_count, total_count, mutation_score, error_message
        """
        # Default implementation: not supported
        return False, {
            "error_message": f"Mutation testing not implemented for {self.language}",
            "killed_count": 0,
            "total_count": 0,
            "mutation_score": 0.0
        }
