"""
Repair Engine for Iterative Test Repair

Core orchestration logic for feedback-based iterative repair of failed tests.
Coordinates LLM calls, test evaluation, and metrics tracking.
"""

import logging
from typing import Callable, Dict, List, Any, Optional
import concurrent.futures

from experiments.evaluation.common.task_ids import normalize_task_id, task_id_sort_key
from experiments.evaluation.repair.prompt_builder import PromptBuilder
from experiments.evaluation.common.result_contract import (
    GenerationResult,
    SUCCESS_STATUS,
    error_result,
    success_result,
    to_response_record,
)


class RepairEngine:
    def __init__(
        self,
        language: str,
        llm_client: Any,
        model: str,
        temperature: float,
        max_workers: int = 1
    ):
        """
        Initialize repair engine for standalone operation.

        Args:
            language: Programming language (go, rust, julia, php, ruby)
            llm_client: OpenAIClient instance
            model: Model name for generation
            temperature: Temperature for generation
        """
        self.language = language.lower()
        self.llm_client = llm_client
        self.model = model
        self.temperature = temperature
        self.max_workers = max_workers

        # Initialize components
        self.prompt_builder = PromptBuilder(language)

    def repair_single_pass(
        self,
        dataset_with_results: List[Dict[str, Any]],
        attempt_number: int = 1,
        on_result: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Run a single repair pass over the dataset.

        Each failed test gets one repair attempt. For multiple attempts,
        call this method multiple times with updated evaluation results.

        Args:
            dataset_with_results: Dataset with evaluation results (logs, checks)
            attempt_number: Which attempt this is (for logging)
            on_result: Optional callback invoked with each repaired-sample record
                as soon as its future resolves (success or exception-fallback).
                Used by callers that want to persist results incrementally
                instead of waiting for the full pass to complete.

        Returns:
            Tuple of (repaired_dataset, metrics_summary)
        """
        print(f"\n{'='*70}")
        print(f"Iterative Repair Pass {attempt_number} for {self.language.upper()}")
        print(f"Model: {self.model}")
        print(f"{'='*70}\n")

        # Track metrics
        total_samples = len(dataset_with_results)

        # Repair each sample (one attempt per failed test)
        repaired_dataset = []

        print(f"Starting repair with {self.max_workers} threads...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks (use sample's task_id if present, otherwise use index)
            future_to_sample = {
                executor.submit(
                    self._repair_sample,
                    sample,
                    normalize_task_id(sample.get('task_id', i)),
                ): (i, sample, normalize_task_id(sample.get('task_id', i)))
                for i, sample in enumerate(dataset_with_results)
            }

            # Process as they complete
            for future in concurrent.futures.as_completed(future_to_sample):
                i, sample, task_id = future_to_sample[future]
                try:
                    repaired_sample = future.result()
                except Exception as exc:
                    print(f"Sample {i} (task_id={task_id}) generated an exception: {exc}")
                    repaired_sample = to_response_record(
                        task_id=task_id,
                        prompt="",
                        result=error_result(f"Exception: {str(exc)}"),
                    )

                repaired_dataset.append(repaired_sample)
                if on_result is not None:
                    on_result(repaired_sample)

                # Optional: Print progress
                completed = len(repaired_dataset)
                total = len(dataset_with_results)
                if completed % 10 == 0 or completed == total:
                    print(f"Progress: {completed}/{total} samples processed")

        # Sort by original task_id if possible to maintain order
        try:
             repaired_dataset.sort(key=lambda x: task_id_sort_key(x.get("task_id")))
        except Exception:
             logging.warning("Failed to sort repaired dataset by task_id", exc_info=True)

        # Compute metrics from the results
        repaired_count = sum(
            1 for r in repaired_dataset if r.get("status") == SUCCESS_STATUS
        )
        metrics_summary = {
            "total_samples": total_samples,
            "repaired_count": repaired_count,
        }

        print(f"\nCompleted repair pass. Processed {len(repaired_dataset)} samples.")

        return repaired_dataset, metrics_summary

    def _repair_sample(self, sample: Dict[str, Any], task_id: int) -> Dict[str, Any]:
        """
        Repair the failed test in a sample.

        Args:
            sample: Sample with initial evaluation results (logs, checks)
            task_id: Index/ID for this sample

        Returns:
            Record dict with task_id, prompt, response, status fields
        """
        # Get test results (each sample has exactly 1 test)
        tests = sample.get("test", [])
        logs = sample.get("logs", [])
        checks = sample.get("checks", [])

        # Process the single test
        if len(tests) == 0:
            return to_response_record(
                task_id=task_id,
                prompt="",
                result=error_result("No test found in sample"),
            )

        test_code = tests[0]
        log = logs[0] if len(logs) > 0 else ""
        check = checks[0] if len(checks) > 0 else {}

        # Check if test failed
        compilation_success = check.get("compilation", False)
        tests_val = check.get("tests", check.get("test", False))
        # If tests_val is a list (per-case results), all entries must pass
        if isinstance(tests_val, list):
            test_pass = all(tests_val)
        else:
            test_pass = bool(tests_val)

        # Build the repair prompt (used regardless of whether repair is needed)
        prompts = self.prompt_builder.build_repair_prompt(
            failed_test=test_code,
            error_log=log,
        )
        prompt_text = prompts["user"]

        if compilation_success and test_pass:
            # Test passed, keep original
            return to_response_record(
                task_id=task_id,
                prompt=prompt_text,
                result=success_result(test_code),
            )

        # Test failed, attempt repair
        result = self._generate_repair_for_test(
            test_code=test_code,
            error_log=log,
        )

        return to_response_record(
            task_id=task_id,
            prompt=prompt_text,
            result=result,
        )

    def _generate_repair_for_test(
        self,
        test_code: str,
        error_log: str
    ) -> GenerationResult:
        """
        Generate a single repair candidate for a failed test.

        Args:
            test_code: Current test code (may already be a previous repair)
            error_log: Error log from evaluation

        Returns:
            GenerationResult with the repaired test code or error
        """
        try:
            # Build repair prompt
            prompts = self.prompt_builder.build_repair_prompt(
                failed_test=test_code,
                error_log=error_log
            )

            # Generate repaired test
            generation = self.llm_client.generate_result(
                prompt=prompts["user"],
                system_prompt=prompts["system"],
                model=self.model,
                temperature=self.temperature
            )

            if not generation.is_success:
                return error_result(f"LLM error: {generation.error}")

            # Store the raw LLM response (markdown). Code extraction happens in preprocessing.
            repaired_test = generation.response
            if not repaired_test or not repaired_test.strip():
                return error_result("Empty repair response from LLM")

            return success_result(repaired_test)

        except Exception as e:
            return error_result(f"Exception: {str(e)}")
