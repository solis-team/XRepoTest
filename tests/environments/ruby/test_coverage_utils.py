from xrepotest.environments.ruby.coverage_utils import (
    extract_coverage_from_text,
    extract_line_cover_info,
)


def test_extract_line_cover_info_parses_simplecov_structure():
    coverage_data = {
        "RSpec": {
            "coverage": {
                "/app/lib/foo.rb": [None, 1, 0, 2, None],
                "/app/src/other.rb": [None, 1, 1, 1],
            }
        },
        "Minitest": {"not_coverage": {}},
    }
    result = extract_line_cover_info(
        coverage_data=coverage_data,
        focal_file_path="/repo/lib/foo.rb",
        focal_start=2,
        focal_end=4,
    )

    assert result == {"covered_lines": 2, "total_lines": 3}


def test_extract_line_cover_info_handles_malformed_data():
    malformed = {"RSpec": 1}
    result = extract_line_cover_info(
        coverage_data=malformed,
        focal_file_path="/repo/lib/foo.rb",
        focal_start=1,
        focal_end=2,
    )
    assert result == {"covered_lines": 0, "total_lines": 0}


def test_extract_coverage_from_text_percentage_fallback_behavior():
    result = extract_coverage_from_text(
        coverage_output="Coverage report generated for RSpec 80.0%",
        focal_file_path="/repo/lib/foo.rb",
        focal_start=10,
        focal_end=14,
    )
    assert result == {"covered_lines": 4, "total_lines": 5}

    no_percentage = extract_coverage_from_text(
        coverage_output="No numeric percentage",
        focal_file_path="/repo/lib/foo.rb",
        focal_start=10,
        focal_end=14,
    )
    assert no_percentage == {"covered_lines": 0, "total_lines": 0}
