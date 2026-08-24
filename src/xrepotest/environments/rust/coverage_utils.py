from collections import defaultdict


def compute_total_coverage(file_result, sample):
    start_line = sample["function_component"]["start_line"]
    end_line = sample["function_component"]["end_line"]
    total_lines = set()
    covered_lines = set()
    branch_map = defaultdict(lambda: [0, 0])

    # --- Branch coverage ---
    for b in file_result.get("branches", []):
        s_line, s_col, e_line, e_col = b[:4]
        true_count, false_count = b[4], b[5]

        # lọc branch trong phạm vi
        if start_line and s_line < start_line:
            continue
        if end_line and e_line > end_line:
            continue

        pos = (s_line, s_col, e_line, e_col)
        branch_map[pos][0] += true_count
        branch_map[pos][1] += false_count

    # --- Line coverage using segments ---
    # Segments in llvm-cov represent points where the execution count changes.
    # Each segment [line, col, count, has_count, is_region_entry] starts a region.
    segments = sorted(file_result.get("segments", []), key=lambda x: (x[0], x[1]))

    for i in range(len(segments)):
        line = segments[i][0]
        count = segments[i][2]
        # Use a defensive check for has_count if present, otherwise assume it has a count if count > 0 or if we want to be safe
        # In llvm-cov JSON, segments usually have 5 elements.
        has_count = segments[i][3] if len(segments[i]) > 3 else True
        
        if not has_count:
            continue

        # Determine the range of lines this segment covers
        # It covers from its start line until the next segment's start line
        start = line
        if i + 1 < len(segments):
            end = segments[i+1][0]
        else:
            # If it's the last segment, we don't know where it ends from the segments alone,
            # but we only care about it up to end_line.
            end = end_line + 1

        # Apply this count to all lines in the range that fall within our focal range
        effective_start = max(start, start_line)
        effective_end = min(end - 1, end_line)

        for l in range(effective_start, effective_end + 1):
            total_lines.add(l)
            if count > 0:
                covered_lines.add(l)

    # --- Tính kết quả ---
    line_coverage = (len(covered_lines) / len(total_lines) * 100) if total_lines else 0

    return {
        "total_lines": len(total_lines),
        "covered_lines": len(covered_lines),
        "line_coverage": round(line_coverage, 2),
    }


def process_coverage(sample, coverage_result_total):
    """
    Process the coverage result and benchmark data.
    """
    res_file = None
    focal_file = sample["file_path"].replace("\\", "/")
    
    # Try multiple strategies to match the focal file in llvm-cov output
    for file in coverage_result_total["data"][0]["files"]:
        filename = file["filename"].replace("\\", "/")
        
        # 1. Exact match
        if focal_file == filename:
            res_file = file
            break
            
        # 2. Suffix match (handles rust-master/src/... vs absolute paths)
        if filename.endswith(focal_file) or focal_file.endswith(filename):
            res_file = file
            break
            
        # 3. Component match (e.g. src/common/buf.rs)
        focal_components = focal_file.split("/")
        if len(focal_components) >= 2:
            # Check for matches like "src/geometry/graham_scan.rs"
            subpath = "/".join(focal_components[-2:])
            if subpath in filename:
                res_file = file
                break
        
        # 4. Basename match as a last resort (if unique)
        if focal_file.split("/")[-1] == filename.split("/")[-1]:
            res_file = file
            # Don't break yet, keep looking for better matches if any
            # but this is a good fallback
            continue

    if res_file is None:
        return None
    
    coverage_stats = compute_total_coverage(res_file, sample)
    return coverage_stats
