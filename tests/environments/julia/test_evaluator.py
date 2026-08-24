from xrepotest.environments.julia.evaluator import JuliaEvaluator

def test_split_dataset_by_repo():
    evaluator = JuliaEvaluator()
    dataset = [
        {"file_path": "DataStructures.jl/src/stack.jl", "function_name": "push"},
        {"file_path": "DataStructures.jl/src/queue.jl", "function_name": "enqueue"},
        {"file_path": "Distributions.jl/src/normal.jl", "function_name": "pdf"},
        {"file_path": "StatsBase.jl/src/counts.jl", "function_name": "counts"},
        {"file_path": "root_file.jl", "function_name": "main"},
    ]

    repo_datasets = evaluator._split_dataset_by_repo(dataset)

    assert "DataStructures.jl" in repo_datasets
    assert "Distributions.jl" in repo_datasets
    assert "StatsBase.jl" in repo_datasets
    assert "unknown" in repo_datasets

    assert len(repo_datasets["DataStructures.jl"]) == 2
    assert len(repo_datasets["Distributions.jl"]) == 1
    assert len(repo_datasets["StatsBase.jl"]) == 1
    assert repo_datasets["unknown"][0]["function_name"] == "main"

    for idx, sample in enumerate(dataset):
        assert sample["task_id"] == idx


def test_merge_coverage_results_maps_checks_and_stats():
    evaluator = JuliaEvaluator()
    samples = [
        {
            "function_name": "foo",
            "test": ["foo(1)"],
            "file_path": "Repo/src/mod.jl",
            "function_component": {"start_line": 1, "end_line": 3},
        }
    ]
    coverage_results = [
        {
            "function_name": "foo",
            "test_idx": 0,
            "pass_rate": 100.0,
            "pass": 3,
            "fail": 0,
            "error": 0,
            "covered_lines": 2,
            "total_lines": 3,
            "log": "ok",
        }
    ]

    evaluator._merge_coverage_results(samples, coverage_results)

    assert samples[0]["checks"][0] == {
        "compilation": True,
        "tests": True,
        "coverage": True,
        "invocation": True,
    }
    assert samples[0]["coverage_stats"][0] == {"covered_lines": 2, "total_lines": 3}
    assert samples[0]["logs"][0] == "ok"


def test_merge_coverage_results_marks_missing_result_as_failed():
    evaluator = JuliaEvaluator()
    samples = [
        {
            "function_name": "foo",
            "test": ["foo(1)", "foo(2)"],
            "file_path": "Repo/src/mod.jl",
            "function_component": {"start_line": 1, "end_line": 3},
        }
    ]
    coverage_results = [
        {
            "function_name": "foo",
            "test_idx": 0,
            "pass_rate": 0.0,
            "pass": 0,
            "fail": 1,
            "error": 0,
            "covered_lines": 0,
            "total_lines": 3,
            "log": "failed",
        }
    ]

    evaluator._merge_coverage_results(samples, coverage_results)

    assert samples[0]["checks"][0]["compilation"] is True
    assert samples[0]["checks"][0]["tests"] is False
    assert samples[0]["checks"][0]["coverage"] is False
    assert samples[0]["checks"][1] == {
        "compilation": False,
        "tests": False,
        "coverage": False,
        "invocation": True,
    }
    assert samples[0]["logs"][1] == "No coverage result found"
    assert samples[0]["coverage_stats"][1] is None


def test_merge_coverage_results_marks_harness_error_as_non_compiling():
    evaluator = JuliaEvaluator()
    samples = [
        {
            "function_name": "foo",
            "test": ["foo(1)"],
            "file_path": "Repo/src/mod.jl",
            "function_component": {"start_line": 1, "end_line": 3},
        }
    ]
    coverage_results = [
        {
            "function_name": "foo",
            "test_idx": 0,
            "pass_rate": 100.0,
            "pass": 1,
            "fail": 0,
            "error": 0,
            "covered_lines": 1,
            "total_lines": 3,
            "harness_error": True,
            "log": "type Tuple has no field passes",
        }
    ]

    evaluator._merge_coverage_results(samples, coverage_results)

    assert samples[0]["checks"][0] == {
        "compilation": False,
        "tests": False,
        "coverage": True,
        "invocation": True,
    }
