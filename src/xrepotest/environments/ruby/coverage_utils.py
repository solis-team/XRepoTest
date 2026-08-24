import re
from typing import Dict, Set


def extract_line_cover_info(
    coverage_data: dict, focal_file_path: str, focal_start: int, focal_end: int
) -> Dict[str, int]:
    """
    Extract line coverage information from SimpleCov .resultset.json coverage data.
    Returns dict with 'covered_lines' and 'total_lines' counts.
    
    Args:
        coverage_data: JSON coverage data from SimpleCov
        focal_file_path: Path to the focal file
        focal_start: Start line of the focal function
        focal_end: End line of the focal function
    
    Returns:
        Dictionary with covered_lines and total_lines
    """
    total_lines: Set[int] = set()
    covered_lines: Set[int] = set()
    
    # Normalize focal file path for comparison
    focal_file_normalized = focal_file_path.replace("\\", "/")
    focal_file_parts = focal_file_normalized.split("/")
    
    # SimpleCov format: { "RSpec": { "coverage": { "filepath": [null, 1, 0, 3, ...] } } }
    try:
        # Navigate through the SimpleCov structure
        for test_suite, suite_data in coverage_data.items():
            if "coverage" not in suite_data:
                continue
            
            coverage = suite_data["coverage"]
            
            for file_path, line_coverage in coverage.items():
                file_path_normalized = file_path.replace("\\", "/")
                
                # Check if this is the focal file
                # Match by filename and parent directory
                if not any(part in file_path_normalized for part in focal_file_parts[-2:]):
                    continue
                
                # line_coverage is an array where index = line number (1-indexed)
                # null = not executable, 0 = not covered, >0 = covered N times
                for line_num, count in enumerate(line_coverage, start=1):
                    # Skip non-executable lines (null)
                    if count is None:
                        continue
                    
                    # Check if line is within focal function range
                    if focal_start <= line_num <= focal_end:
                        total_lines.add(line_num)
                        if count > 0:
                            covered_lines.add(line_num)
    except (KeyError, TypeError, ValueError) as e:
        print(f"Error parsing coverage data: {e}")
        return {
            "covered_lines": 0,
            "total_lines": 0,
        }
    
    return {
        "covered_lines": len(covered_lines),
        "total_lines": len(total_lines),
    }


def extract_coverage_from_text(
    coverage_output: str, focal_file_path: str, focal_start: int, focal_end: int
) -> Dict[str, int]:
    """
    Extract coverage from RSpec/SimpleCov text output (fallback method).
    
    Args:
        coverage_output: Text output from RSpec
        focal_file_path: Path to the focal file
        focal_start: Start line of the focal function
        focal_end: End line of the focal function
    
    Returns:
        Dictionary with covered_lines and total_lines (estimates)
    """
    # This is a fallback method - coverage from text is imprecise
    # Look for coverage percentage in output
    coverage_pattern = r"(\d+(?:\.\d+)?)%"
    matches = re.findall(coverage_pattern, coverage_output)
    
    if matches:
        # Use the first percentage found
        try:
            percentage = float(matches[0])
            # Estimate based on function line count
            total_lines_count = focal_end - focal_start + 1
            covered_count = int(total_lines_count * percentage / 100)
            
            return {
                "covered_lines": covered_count,
                "total_lines": total_lines_count,
            }
        except ValueError:
            pass
    
    return {
        "covered_lines": 0,
        "total_lines": 0,
    }
