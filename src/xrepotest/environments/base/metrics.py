"""
Shared metrics calculation module for xrepotest evaluation pipeline.

This module provides a centralized summary calculation function used across
all language evaluations (Rust, Go, Julia, PHP, Ruby) to ensure consistency
and eliminate code duplication.
"""

from typing import Dict, Any, List


def calculate_summary(
    dataset: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calculate evaluation summary metrics directly from dataset fields.
    
    Args:
        dataset: List of evaluated samples, each containing:
            - test: List of test codes
            - checks: List of dicts with {compilation, tests, coverage, invocation, mutation (optional)}
            - coverage_stats: List of dicts with {covered_lines, total_lines}
            - mutation_scores: List of dicts with mutation results (optional)
    
    Returns:
        Dictionary containing summary metrics:
            - total_samples: Number of samples evaluated
            - compiled_rate: Percentage of tests that compiled (0-100)
            - line_coverage: Macro-averaged line coverage percentage (0-100), equal weight per focal function
            - test_pass_rate: Percentage of tests that passed (0-100)
            - invocation_rate: Percentage of tests invoking focal function (0-100)
            - mutation_testing: Optional nested dict with mutation statistics (if present)
    """
    if not dataset:
        return {
            "total_samples": 0,
            "compiled_rate": 0.0,
            "line_coverage": 0.0,
            "test_pass_rate": 0.0,
            "invocation_rate": 0.0,
        }
    
    # Calculate n_responses_per_sample
    n_responses_per_sample = max(len(sample.get("test", [])) for sample in dataset)
    total_test = n_responses_per_sample * len(dataset)
    
    # Extract metrics from dataset
    compilation_success_count = 0
    test_pass = 0
    sum_line_coverage_pct = 0.0
    total_invoked_tests = 0
    
    # Mutation testing metrics
    mutation_tests_run = 0
    total_mutants_killed = 0
    total_mutants_count = 0
    has_mutation_data = False
    
    for sample in dataset:
        # Count from checks
        for check in sample.get("checks", []):
            if check.get("compilation", False):
                compilation_success_count += 1
            if check.get("tests", False):
                test_pass += 1
            if check.get("invocation", False):
                total_invoked_tests += 1
            
            # Check if mutation testing was run
            if check.get("mutation", False):
                mutation_tests_run += 1
                has_mutation_data = True
        
        # Aggregate coverage using macro-averaging (equal weight per sample)
        # Each sample contributes (covered/total)*100; missing data contributes 0%
        # Final result is the average of per-sample coverage rates
        coverage_stats = sample.get("coverage_stats", [])
        for i in range(n_responses_per_sample):
            if i < len(coverage_stats) and isinstance(coverage_stats[i], dict):
                stat = coverage_stats[i]
                covered = stat.get("covered_lines", 0)
                total = stat.get("total_lines", 0)
                if total > 0:
                    sum_line_coverage_pct += (covered / total) * 100.0
            # If no coverage data for this response slot, it adds 0.0% (implicitly)
        
        # Aggregate mutation scores
        for mutation_score in sample.get("mutation_scores", []):
            if mutation_score is not None:
                total_mutants_killed += mutation_score.get("killed_count", 0)
                total_mutants_count += mutation_score.get("total_count", 0)
    
    # Calculate core metrics with safe division
    compiled_rate = (
        compilation_success_count / total_test * 100 
        if total_test > 0 else 0.0
    )
    
    test_pass_rate = (
        test_pass / total_test * 100 
        if total_test > 0 else 0.0
    )
    
    line_coverage = (
        sum_line_coverage_pct / total_test 
        if total_test > 0 else 0.0
    )
    
    invoke_rate = (
        total_invoked_tests / total_test * 100 
        if total_test > 0 else 0.0
    )
    
    # Build core summary
    summary = {
        "total_samples": len(dataset),
        "compiled_rate": compiled_rate,
        "line_coverage": line_coverage,
        "test_pass_rate": test_pass_rate,
        "invocation_rate": invoke_rate,
    }
    
    # Add mutation testing metrics if data exists
    if has_mutation_data:
        # Calculate aggregate mutation score (0.0 to 1.0)
        avg_mutation_score = (
            total_mutants_killed / total_mutants_count
            if total_mutants_count > 0 else 0.0
        )
        
        # Calculate mutation run rate (% of passed tests that ran mutation)
        mutation_run_rate = (
            mutation_tests_run / test_pass * 100
            if test_pass > 0 else 0.0
        )
        
        summary["mutation_testing"] = {
            "mutation_tests_run": mutation_tests_run,
            "total_mutants_killed": total_mutants_killed,
            "total_mutants_count": total_mutants_count,
            "avg_mutation_score": avg_mutation_score,
            "mutation_run_rate": mutation_run_rate,
        }
    
    return summary
