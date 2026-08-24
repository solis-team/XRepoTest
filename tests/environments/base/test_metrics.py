import pytest

from xrepotest.environments.base.metrics import calculate_summary


def test_calculate_summary_empty_dataset_returns_zeroed_core_summary():
    assert calculate_summary([]) == {
        "total_samples": 0,
        "compiled_rate": 0.0,
        "line_coverage": 0.0,
        "test_pass_rate": 0.0,
        "invocation_rate": 0.0,
    }


def test_calculate_summary_non_empty_dataset_computes_core_rates():
    # n_responses_per_sample = 2
    # total_test = 4
    dataset = [
        {
            "test": ["t1", "t2"],
            "checks": [
                {"compilation": True, "tests": True, "invocation": True},
                {"compilation": False, "tests": False, "invocation": False},
            ],
            "coverage_stats": [
                {"covered_lines": 3, "total_lines": 10},  # 30%
                {"covered_lines": 1, "total_lines": 10},  # 10%
            ],
        },
        {
            "test": ["t3", "t4"],
            "checks": [
                {"compilation": True, "tests": True, "invocation": False},
                {"compilation": True, "tests": False, "invocation": False},
            ],
            "coverage_stats": [
                {"covered_lines": 1, "total_lines": 10},  # 10%
                # Missing second response stats -> 0%
            ],
        },
    ]

    summary = calculate_summary(dataset)

    assert summary["total_samples"] == 2
    assert summary["compiled_rate"] == pytest.approx(75.0)
    assert summary["test_pass_rate"] == pytest.approx(50.0)
    assert summary["invocation_rate"] == pytest.approx(25.0)
    # Average of (30% + 10% + 10% + 0%) / 4 = 50% / 4 = 12.5%
    assert summary["line_coverage"] == pytest.approx(12.5)
    assert "mutation_testing" not in summary


def test_calculate_summary_includes_mutation_testing_only_when_present():
    dataset = [
        {
            "test": ["t1", "t2"],
            "checks": [
                {"compilation": True, "tests": True, "invocation": True, "mutation": True},
                {"compilation": True, "tests": True, "invocation": False, "mutation": False},
            ],
            "coverage_stats": [
                {"covered_lines": 4, "total_lines": 20} # 20%
                # Missing second response stats -> 0%
            ],
            "mutation_scores": [
                {"killed_count": 3, "total_count": 5},
                {"killed_count": 1, "total_count": 5},
            ],
        }
    ]

    summary = calculate_summary(dataset)

    assert "mutation_testing" in summary
    assert summary["mutation_testing"] == {
        "mutation_tests_run": 1,
        "total_mutants_killed": 4,
        "total_mutants_count": 10,
        "avg_mutation_score": pytest.approx(0.4),
        "mutation_run_rate": pytest.approx(50.0),
    }
    # Average of (20% + 0%) / 2 = 10%
    assert summary["line_coverage"] == pytest.approx(10.0)
