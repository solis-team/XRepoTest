import re
import xml.etree.ElementTree as ET
from typing import Dict, Set


def extract_line_cover_info(
    coverage_data: str, focal_file_path: str, focal_start: int, focal_end: int
) -> Dict[str, int]:
    """
    Extract line coverage information from PHPUnit clover.xml coverage data.
    Returns dict with 'covered_lines' and 'total_lines' counts.
    
    Args:
        coverage_data: XML coverage data from PHPUnit clover format
        focal_file_path: Path to the focal file
        focal_start: Start line of the focal function
        focal_end: End line of the focal function
    
    Returns:
        Dictionary with covered_lines and total_lines
    """
    try:
        root = ET.fromstring(coverage_data)
    except ET.ParseError:
        return {
            "covered_lines": 0,
            "total_lines": 0,
        }
    
    total_lines: Set[int] = set()
    covered_lines: Set[int] = set()
    
    # Normalize focal file path for comparison
    focal_file_normalized = focal_file_path.replace("\\", "/")
    focal_file_parts = focal_file_normalized.split("/")
    
    # Find all file elements in the coverage report
    for file_elem in root.iter("file"):
        file_name = file_elem.get("name", "")
        file_name_normalized = file_name.replace("\\", "/")
        
        # Check if this is the focal file
        # Match by filename and parent directory
        if not any(part in file_name_normalized for part in focal_file_parts[-2:]):
            continue
        
        # Parse line elements
        for line_elem in file_elem.iter("line"):
            try:
                line_num = int(line_elem.get("num", 0))
                line_type = line_elem.get("type", "")
                count = int(line_elem.get("count", 0))
                
                # Only consider executable lines (method statements)
                if line_type != "stmt":
                    continue
                
                # Check if line is within focal function range
                if focal_start <= line_num <= focal_end:
                    total_lines.add(line_num)
                    if count > 0:
                        covered_lines.add(line_num)
            except (ValueError, TypeError):
                continue
    
    return {
        "covered_lines": len(covered_lines),
        "total_lines": len(total_lines),
    }


def extract_coverage_from_text(
    coverage_output: str, focal_file_path: str, focal_start: int, focal_end: int
) -> Dict[str, int]:
    """
    Extract coverage from PHPUnit text output (fallback method).
    
    Args:
        coverage_output: Text output from PHPUnit
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
