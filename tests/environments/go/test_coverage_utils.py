from xrepotest.environments.go.coverage_utils import (
    extract_branch_coverage,
    extract_line_cover_info,
)


def test_extract_line_cover_info_filters_range_and_ignores_malformed_lines():
    coverage_data = "\n".join(
        [
            "mode: set",
            "github.com/acme/pkg/file.go:10.1,12.2 1 3",
            "github.com/acme/pkg/file.go:13.1,15.2 1 0",
            "github.com/acme/other/file.go:11.1,12.2 1 1",
            "malformed line",
            "github.com/acme/pkg/file.go:bogus,14.2 1 1",
        ]
    )

    result = extract_line_cover_info(
        coverage_data=coverage_data,
        focal_file_path="/repo/pkg/file.go",
        focal_start=11,
        focal_end=14,
    )

    assert result == {"covered_lines": 2, "total_lines": 4}


def test_extract_branch_coverage_handles_normal_never_evaluated_and_single_sided_cases():
    gobco_output = "\n".join(
        [
            "/repo/pkg/file.go:20:5: condition x > 0 3 times true and 0 times false",
            "/repo/pkg/file.go:21:5: condition y was never evaluated",
            "/repo/pkg/file.go:22:5: condition z was once true but never false",
            "/repo/pkg/file.go:23:5: condition k was once false but never true",
            "/repo/pkg/file.go:30:5: condition out 1 times true and 1 times false",
        ]
    )

    covered, total = extract_branch_coverage(gobco_output, start_line=20, end_line=25)

    assert covered == 3
    assert total == 8
