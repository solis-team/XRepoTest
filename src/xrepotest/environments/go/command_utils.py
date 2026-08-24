import subprocess
import os
from pathlib import Path
from typing import Tuple, Dict, Any

from .coverage_utils import extract_line_cover_info
from .test_utils import extract_test_function_names, build_test_run_pattern

# Ensure Go modules are enabled
env = os.environ.copy()
env["GO111MODULE"] = "on"


def get_package_dir(file_path: str) -> Path:
    """
    Get the directory containing the test file.
    """
    return Path(file_path).parent


def check_compilation(test_file_path: str, test_code: str) -> Tuple[bool, str]:
    """
    Check the compilation of the test file by attempting to build the test binary
    without executing the tests. Uses the -run flag with a pattern matching
    the tests in the file to isolate the check.
    
    Args:
        test_file_path: Path to the test file (e.g., utils_test.go)
        test_code: Source code of the test file
    
    Returns:
        A tuple of (success: bool, output: str)
    """
    package_dir = get_package_dir(test_file_path)

    # Extract test names and build pattern
    test_names = extract_test_function_names(test_code)
    if test_names:
        command = ["go", "test", "-c"]
    else:
        # No test functions found, return error
        return False, "No test functions found in test code"

    try:
        result = subprocess.run(
            command,
            cwd=package_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        output = result.stdout.strip() or result.stderr.strip()
        return True, output
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        error_log = (e.stderr or "") + "\n" + (e.stdout or "")
        return False, error_log.strip() or "Compilation failed with no output."
    except Exception as e:
        return False, f"An unexpected error occurred: {e}"


def check_test(test_file_path: str, test_code: str) -> Tuple[bool, str]:
    """
    Run all test functions within a specific Go test file.
    
    Args:
        test_file_path: Path to the test file (e.g., utils_test.go)
        test_code: Source code of the test file
    
    Returns:
        A tuple of (success: bool, log: str)
    """
    package_dir = get_package_dir(test_file_path)

    # Extract test names and build pattern
    test_names = extract_test_function_names(test_code)
    if test_names:
        run_pattern = build_test_run_pattern(test_names)
        command = ["go", "test", "-v", "-run", run_pattern]
    else:
        # No test functions found, return error
        return False, "No test functions found in test code"
    

    try:
        result = subprocess.run(
            command,
            cwd=package_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        return True, result.stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        error_log = (e.stderr or "") + "\n" + (e.stdout or "")
        return False, error_log.strip() or "Test failed with no output."
    except Exception as e:
        return False, f"An unexpected error occurred: {e}"


def generate_coverage_report(
    test_file_path: str,
    test_code: str,
    file_path: str, 
    start_line: int, 
    end_line: int
) -> Tuple[bool, Any]:
    """
    Generate a code coverage report for a specific Go test file, focused on a target function range.
    
    Args:
        test_file_path: Path to the test file
        test_code: Source code of the test file
        file_path: Path to the focal source file
        start_line: Start line of the focal function in the source file
        end_line: End line of the focal function in the source file
    
    Returns:
        A tuple of (success: bool, summary: dict or error_msg: str)
    """
    package_dir = get_package_dir(test_file_path)
    coverage_file = Path(package_dir) / "coverage.out"

    try:
        # Extract test names and build pattern
        test_names = extract_test_function_names(test_code)
        if test_names:
            run_pattern = build_test_run_pattern(test_names)
            command = [
                "go", "test",
                "-coverprofile=coverage.out",
                "-run", run_pattern
            ]
        else:
            # No test functions found, return error
            return False, "No test functions found in test code"
        
        subprocess.run(
            command,
            cwd=package_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )

        if not coverage_file.exists():
            raise FileNotFoundError("coverage.out file does not exist")

        with open(coverage_file, "r") as f:
            line_data = f.read()

        # Extract coverage information
        summary = extract_line_cover_info(
            line_data,
            file_path,
            start_line,
            end_line,
        )

        return True, summary

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        error_log = (e.stderr or "") + "\n" + (e.stdout or "")
        return (False, error_log.strip()
                or "Coverage report generation failed with no output.", )
    except Exception as e:
        return False, f"An unexpected error occurred: {e}"
    
def run_mutation_score(
    focal_file_path: str,
    focal_function_name: str,
    timeout: int = 600
) -> Tuple[bool, Dict[str, Any]]:
    """
    Run mutation testing on a specific function and return the mutation score.
    
    Args:
        focal_file_path: Path to the file containing the function to test (e.g., utils.go)
        focal_function_name: Name of the function to mutation test (e.g., "Add")
        timeout: Timeout in seconds (default: 300)
    
    Returns:
        Tuple[bool, Dict[str, Any]]: (success, result_dict)
        - success: True if execution was successful, False if there was an error
        - result_dict: Dictionary containing mutation score information:
            {
                "mutation_score": float,  # MSI (Mutation Score Indicator)
                "killed_count": int,      # Number of mutants detected (PASS)
                "escaped_count": int,     # Number of mutants not detected (FAIL)
                "duplicated_count": int,  # Number of duplicate mutants
                "skipped_count": int,     # Number of skipped mutants (did not compile)
                "total_count": int,       # Total number of mutants
                "error_message": str      # Error message if any
            }
    
    Note:
        - Uses focal_file_path to determine the package directory
        - go-mutesting will automatically find and run all tests in the package
    """
    # Validate focal file exists
    if not Path(focal_file_path).exists():
        return False, {
            "mutation_score": 0.0,
            "killed_count": 0,
            "escaped_count": 0,
            "duplicated_count": 0,
            "skipped_count": 0,
            "total_count": 0,
            "error_message": f"Focal file not found: {focal_file_path}"
        }
    
    # Use focal_file_path to determine package directory
    package_dir = Path(focal_file_path).parent
    
    # Initialize result dictionary
    result: Dict[str, Any] = {
        "mutation_score": 0.0,
        "killed_count": 0,
        "escaped_count": 0,
        "duplicated_count": 0,
        "skipped_count": 0,
        "total_count": 0,
        "error_message": ""
    }
    
    try:
        # Prepare environment - inherit current env and ensure Go is available
        run_env = os.environ.copy()
        
        # Run go-mutesting
        # go-mutesting outputs results to stdout, not a JSON file
        command = [
            "go-mutesting",
            "--match", f"^{focal_function_name}$",
            "."
        ]
        
        mutation_result = subprocess.run(
            command,
            cwd=package_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=run_env,
        )
        
        # Parse stdout output from go-mutesting
        stdout = mutation_result.stdout
        stderr = mutation_result.stderr
        
        # Check for critical errors
        if "no Go files" in stderr or "no buildable Go source files" in stderr:
            result["error_message"] = f"No Go files found: {stderr}"
            return False, result
        
        import re
        
        # go-mutesting output format varies by version:
        # 1. Summary line: "The mutation score is X.XXXXXX (Y killed, Z escaped, W skipped, total is T)"
        # 2. Or individual results with PASS/FAIL lines
        
        # Try parsing summary line first
        score_pattern = r"The mutation score is ([\d.]+) \((\d+) killed, (\d+) escaped, (\d+) skipped, total is (\d+)\)"
        match = re.search(score_pattern, stdout)
        
        if match:
            result["mutation_score"] = float(match.group(1))
            result["killed_count"] = int(match.group(2))
            result["escaped_count"] = int(match.group(3))
            result["skipped_count"] = int(match.group(4))
            result["total_count"] = int(match.group(5))
            
            if result["total_count"] == 0:
                result["error_message"] = "No mutants were generated. Check if the function exists and is testable."
                return False, result
            
            return True, result
        
        # Alternative parsing: count PASS and FAIL lines
        # PASS = mutant was killed (test caught the mutation)
        # FAIL = mutant escaped (test did not catch the mutation)
        pass_count = len(re.findall(r'^PASS\s', stdout, re.MULTILINE))
        fail_count = len(re.findall(r'^FAIL\s', stdout, re.MULTILINE))
        
        total = pass_count + fail_count
        
        if total > 0:
            result["killed_count"] = pass_count
            result["escaped_count"] = fail_count
            result["total_count"] = total
            result["mutation_score"] = pass_count / total if total > 0 else 0.0
            return True, result
        
        # No mutations found
        if "0 mutations" in stdout or total == 0:
            result["error_message"] = "No mutants were generated for this function."
            return False, result
        
        # Could not parse output
        result["error_message"] = f"Could not parse go-mutesting output.\nStdout: {stdout[:500]}\nStderr: {stderr[:500]}"
        return False, result
        
    except subprocess.TimeoutExpired:
        result["error_message"] = f"Mutation testing timeout (exceeded {timeout} seconds)"
        return False, result
    except FileNotFoundError as e:
        result["error_message"] = f"go-mutesting not found. Make sure it's installed: {e}"
        return False, result
    except PermissionError as e:
        result["error_message"] = f"Permission denied: {e}"
        return False, result
    except Exception as e:
        result["error_message"] = f"An unexpected error occurred: {type(e).__name__}: {e}"
        return False, result
