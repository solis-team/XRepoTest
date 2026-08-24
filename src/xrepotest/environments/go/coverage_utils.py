import re
from typing import Dict, Tuple, Set


def extract_line_cover_info(
    coverage_data: str, focal_file_path: str, focal_start: int, focal_end: int
) -> Dict[str, int]:
    """
    Extract line coverage information from coverage data.
    Returns dict with 'covered_lines' and 'total_lines' counts.
    """
    package_and_name = "/".join(focal_file_path.split("/")[-2:])
    total_lines: Set[int] = set()
    covered_lines: Set[int] = set()

    for line in coverage_data.split("\n"):
        if line.startswith("mode:") or len(line.split()) < 3:
            continue

        try:
            parts = line.split()
            file_info = parts[0]
            covered_file_path = file_info.split(":")[0]

            if package_and_name not in covered_file_path:
                continue

            block_start = int(file_info.split(":")[1].split(".")[0])
            block_end = int(file_info.split(",")[1].split(".")[0])
            count = int(parts[2])

            effective_start = max(block_start, focal_start)
            effective_end = min(block_end, focal_end)

            if effective_start <= effective_end:
                for line_num in range(effective_start, effective_end + 1):
                    total_lines.add(line_num)
                    if count > 0:
                        covered_lines.add(line_num)
        except (ValueError, IndexError, AttributeError):
            continue

    return {
        "covered_lines": len(covered_lines),
        "total_lines": len(total_lines),
    }


def extract_branch_coverage(
    gobco_output: str, start_line: int, end_line: int
) -> Tuple[int, int]:
    """
    Extract branch coverage from gobco output.
    Returns tuple of (covered_branches, total_branches).
    """
    covered = 0
    total = 0
    pattern = re.compile(
        r".+?:(\d+):\d+: condition .*? (\d+) times true.*?(\d+) times false"
    )

    for line in gobco_output.splitlines():
        match = pattern.match(line)
        if match:
            line_num = int(match.group(1))
            if start_line <= line_num <= end_line:
                true_count = int(match.group(2))
                false_count = int(match.group(3))
                covered += (1 if true_count > 0 else 0) + \
                    (1 if false_count > 0 else 0)
                total += 2
        elif "was never evaluated" in line:
            match = re.match(r".+?:(\d+):\d+: condition", line)
            if match and start_line <= int(match.group(1)) <= end_line:
                total += 2
        elif (
            "was once true but never false" in line
            or "was once false but never true" in line
        ):
            match = re.match(r".+?:(\d+):\d+: condition", line)
            if match and start_line <= int(match.group(1)) <= end_line:
                covered += 1
                total += 2

    return covered, total
