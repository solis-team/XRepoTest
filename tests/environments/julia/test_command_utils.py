import json

from xrepotest.environments.julia.command_utils import parse_coverage_results


def test_parse_coverage_results_aggregates_and_preserves_rows(tmp_path):
    report = tmp_path / "report.jsonl"
    rows = [
        {
            "function_name": "foo",
            "test_idx": 0,
            "pass": 1,
            "fail": 0,
            "error": 0,
            "covered_lines": 2,
            "total_lines": 4,
        },
        {
            "function_name": "foo",
            "test_idx": 1,
            "pass": 0,
            "fail": 1,
            "error": 1,
            "covered_lines": 1,
            "total_lines": 4,
        },
    ]
    report.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    parsed = parse_coverage_results(str(report))

    assert parsed["covered_lines"] == 3
    assert parsed["total_lines"] == 8
    assert parsed["pass"] == 1
    assert parsed["fail"] == 1
    assert parsed["error"] == 1
    assert parsed["results"] == rows


def test_parse_coverage_results_returns_zeroes_for_missing_file(tmp_path):
    parsed = parse_coverage_results(str(tmp_path / "missing.jsonl"))

    assert parsed == {
        "covered_lines": 0,
        "total_lines": 0,
        "pass": 0,
        "fail": 0,
        "error": 0,
    }


def test_parse_coverage_results_skips_malformed_json_lines(tmp_path):
    report = tmp_path / "report.jsonl"
    report.write_text(
        "\n".join(
            [
                '{"function_name":"foo","test_idx":0,"pass":1,"fail":0,"error":0,"covered_lines":2,"total_lines":4}',
                '{"malformed"',
            ]
        ),
        encoding="utf-8",
    )

    parsed = parse_coverage_results(str(report))

    assert parsed["covered_lines"] == 2
    assert parsed["total_lines"] == 4
    assert parsed["pass"] == 1
    assert parsed["fail"] == 0
    assert parsed["error"] == 0
    assert len(parsed["results"]) == 1
