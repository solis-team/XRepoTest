from xrepotest.environments.php.coverage_utils import (
    extract_coverage_from_text,
    extract_line_cover_info,
)


def test_extract_line_cover_info_parses_stmt_lines_in_focal_range():
    clover_xml = """
    <coverage>
      <project>
        <file name="/app/src/Foo.php">
          <line num="9" type="stmt" count="1"/>
          <line num="10" type="stmt" count="1"/>
          <line num="11" type="stmt" count="0"/>
          <line num="12" type="stmt" count="2"/>
          <line num="12" type="method" count="99"/>
          <line num="bad" type="stmt" count="1"/>
        </file>
      </project>
    </coverage>
    """
    result = extract_line_cover_info(
        coverage_data=clover_xml,
        focal_file_path="/repo/src/Foo.php",
        focal_start=10,
        focal_end=12,
    )

    assert result == {"covered_lines": 2, "total_lines": 3}


def test_extract_line_cover_info_returns_zeros_on_xml_parse_error():
    result = extract_line_cover_info(
        coverage_data="<coverage><broken>",
        focal_file_path="/repo/src/Foo.php",
        focal_start=1,
        focal_end=2,
    )
    assert result == {"covered_lines": 0, "total_lines": 0}


def test_extract_coverage_from_text_percentage_fallback_behavior():
    result = extract_coverage_from_text(
        coverage_output="Lines: 66.7%",
        focal_file_path="/repo/src/Foo.php",
        focal_start=5,
        focal_end=9,
    )
    assert result == {"covered_lines": 3, "total_lines": 5}

    no_percentage = extract_coverage_from_text(
        coverage_output="No percentage present",
        focal_file_path="/repo/src/Foo.php",
        focal_start=5,
        focal_end=9,
    )
    assert no_percentage == {"covered_lines": 0, "total_lines": 0}
