from xrepotest.environments.rust.coverage_utils import (
    compute_total_coverage,
    process_coverage,
)


def test_compute_total_coverage_computes_stats_within_function_range():
    sample = {
        "file_path": "src/lib.rs",
        "function_component": {"start_line": 10, "end_line": 12},
    }
    file_result = {
        "segments": [
            [9, 0, 2],
            [10, 0, 1],
            [11, 0, 0],
            [12, 0, 3],
            [13, 0, 1],
        ],
        "branches": [
            [10, 1, 10, 5, 1, 0],
            [8, 1, 8, 5, 1, 1],
        ],
    }

    result = compute_total_coverage(file_result, sample)

    assert result == {"total_lines": 3, "covered_lines": 2, "line_coverage": 66.67}


def test_process_coverage_returns_none_when_focal_file_missing():
    sample = {
        "file_path": "src/lib.rs",
        "function_component": {"start_line": 1, "end_line": 2},
    }
    coverage_result_total = {"data": [{"files": [{"filename": "src/other.rs", "segments": []}]}]}

    assert process_coverage(sample, coverage_result_total) is None


def test_process_coverage_returns_stats_when_focal_file_found():
    sample = {
        "file_path": "src/lib.rs",
        "function_component": {"start_line": 2, "end_line": 4},
    }
    coverage_result_total = {
        "data": [
            {
                "files": [
                    {"filename": "src/other.rs", "segments": [[2, 0, 1]], "branches": []},
                    {
                        "filename": "/workspace/project/src/lib.rs",
                        "segments": [[2, 0, 1], [3, 0, 0], [4, 0, 1]],
                        "branches": [],
                    },
                ]
            }
        ]
    }

    result = process_coverage(sample, coverage_result_total)

    assert result == {"total_lines": 3, "covered_lines": 2, "line_coverage": 66.67}
