import subprocess
import os
import json
from typing import Tuple, Dict

# Julia environment
env = os.environ.copy()



def run_julia_command(
    command: list, cwd: str = None, timeout: int = 300
) -> Tuple[bool, str]:
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )

        output_lines = []

        for line in process.stdout:
            # print(line, end="")      # stream to terminal
            output_lines.append(line)

        process.wait(timeout=timeout)
        success = process.returncode == 0

        return success, "".join(output_lines)

    except subprocess.TimeoutExpired:
        process.kill()
        return False, f"Command timed out after {timeout}s"

    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

def run_julia_coverage(
    repo_path: str, test_file: str, output_dir: str
) -> Tuple[bool, str]:
    """
    Run Julia coverage analysis using run_coverage.jl script.

    Args:
        repo_path: Path to the Julia repository
        test_file: Path to the test JSONL file
        output_dir: Directory to save coverage results

    Returns:
        Tuple of (success, log_output)
    """
    command = [
        "julia",
        "--project=.",
        "/app/run_coverage.jl",
        f"--repo={repo_path}",
        f"--test={test_file}",
        f"--output={output_dir}",
    ]

    # 10 minute timeout for coverage
    return run_julia_command(command, timeout=600)


def parse_coverage_results(report_file: str) -> Dict:
    """
    Parse Julia coverage results from JSONL report file.

    Args:
        report_file: Path to the coverage report JSONL file

    Returns:
        Dictionary with coverage statistics
    """
    if not os.path.exists(report_file):
        return {
            "covered_lines": 0,
            "total_lines": 0,
            "pass": 0,
            "fail": 0,
            "error": 0}

    results = []
    with open(report_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    data = json.loads(line)
                    results.append(data)
                except json.JSONDecodeError as e:
                    print(f"Error parsing result line: {e}")

    # Aggregate results
    total_covered = sum(r.get("covered_lines", 0) for r in results)
    total_lines = sum(r.get("total_lines", 0) for r in results)
    total_pass = sum(r.get("pass", 0) for r in results)
    total_fail = sum(r.get("fail", 0) for r in results)
    total_error = sum(r.get("error", 0) for r in results)

    return {
        "covered_lines": total_covered,
        "total_lines": total_lines,
        "pass": total_pass,
        "fail": total_fail,
        "error": total_error,
        "results": results,
    }


