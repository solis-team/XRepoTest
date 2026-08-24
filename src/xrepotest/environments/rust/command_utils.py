import subprocess
from pathlib import Path
import json
import os
import re
import shutil
from typing import Dict, Any, Tuple

from .coverage_utils import process_coverage
from .test_utils import get_project_dir

env = os.environ.copy()
env["RUSTFLAGS"] = "-Awarnings"

def build_command(file_path: str, test_name: str):
    """
    Build the cargo test filter. 
    Instead of complex path mapping, we use the unique suffix 'tests_xrepotest' 
    which we ensure is used in format_test_code.
    """
    return "tests_xrepotest"


def generate_coverage_report(file_path: str, test_name: str, sample=None):
    project_dir = get_project_dir(file_path)
    test_filter = build_command(file_path, test_name)

    if not project_dir or not os.path.isdir(project_dir):
        return False, f"Project directory not found: {project_dir}"

    command = [
        "cargo", "llvm-cov",
        "--json",
        "--branch",
        "--ignore-run-fail",
        "test",
        test_filter
    ]

    try:
        result = subprocess.run(
            command,
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
            env=env,
        )

        try:
            coverage_data = json.loads(result.stdout)
            
            if sample is not None:
                coverage_stats = process_coverage(sample, coverage_data)
                return True, coverage_stats
            
            return True, coverage_data
        except json.JSONDecodeError as e:
            return False, f"Failed to parse coverage JSON: {str(e)}\nRaw output: {result.stdout}"

    except subprocess.CalledProcessError as e:
        error_msg = (e.stderr or e.stdout or "Command failed with no output").strip()
        return False, error_msg

    except subprocess.TimeoutExpired as e:
        error_msg = (e.stderr or e.stdout or "Coverage generation timed out").strip()
        return False, error_msg

    except Exception as e:
        return False, f"Unexpected error: {str(e)}"
    
def check_test(file_path: str, test_name: str):
    project_dir = get_project_dir(file_path)
    test_filter = build_command(file_path, test_name)
    command = ["cargo", "test", test_filter]

    try:
        result = subprocess.run(
            command,
            cwd=project_dir,
            check=False, # Check output manually for true passes
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        
        output = result.stdout + "\n" + result.stderr
        
        # Verify that tests actually ran and passed
        # Example line: "test result: ok. 1 passed; 0 failed; ..."
        match = re.search(r"test result: ok\. (\d+) passed; 0 failed", output)
        
        if match:
            passed_count = int(match.group(1))
            if passed_count > 0:
                return True, output.strip()
            else:
                return False, output.strip() + "\nERROR: 0 tests were executed. Filter might be incorrect."
        
        # If there's an explicit failure line
        if "test result: FAILED" in output or "FAILED" in output:
             return False, output.strip()

        return False, output.strip() or "test failed or was not executed"
        
    except subprocess.TimeoutExpired as e:
        error_log = (e.stderr or "") + "\n" + (e.stdout or "")
        return False, error_log.strip() or "test timed out"
        
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"
# 
def check_compilation(file_path: str, test_name: str):

    project_dir = get_project_dir(file_path)

    if not project_dir or not os.path.isdir(project_dir):
        return False, f"Project directory not found: {project_dir}"
    
    command = [
        "cargo",
        "check",
        "--tests",  # Ensure we check the tests
    ]
    
    try:
        result = subprocess.run(
            command,
            cwd=project_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,  # Use copy of current environment
        )
        
        # Combine stdout and stderr since cargo may output warnings to stderr
        log = (result.stdout + "\n" + result.stderr).strip()
        return True, log
        
    except subprocess.CalledProcessError as e:
        # Combine outputs and ensure we return a string
        error_log = (e.stderr or "") + "\n" + (e.stdout or "")
        return False, error_log.strip() or "Compilation failed with no output"
        
    except subprocess.TimeoutExpired as e:
        error_log = (e.stderr or "") + "\n" + (e.stdout or "")
        return False, error_log.strip() or "Compilation timed out"
        
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


def run_mutation_score(
    focal_file_path: str,
    focal_function_name: str,
    timeout: int = 600
) -> Tuple[bool, Dict[str, Any]]:
    """
    Run mutation testing on a specific Rust function and return the mutation score.
    
    Args:
        focal_file_path: Path to the file containing the function to test (e.g., src/lib.rs)
        focal_function_name: Name of the function to mutation test (e.g., "add")
        timeout: Timeout in seconds (default: 300)
    
    Returns:
        Tuple[bool, Dict[str, Any]]: (success, result_dict)
        - success: True if execution was successful, False if there was an error
        - result_dict: Dictionary containing mutation score information:
            {
                "mutation_score": float,  # MSI (Mutation Score Indicator) 0.0-1.0
                "killed_count": int,      # Number of mutants detected (caught)
                "escaped_count": int,     # Number of mutants not detected (missed)
                "duplicated_count": int,  # Number of timeout mutants (mapped from timeout)
                "skipped_count": int,     # Number of skipped mutants (unviable)
                "total_count": int,       # Total number of mutants
                "error_message": str      # Error message if any
            }
    
    Note:
        - Requires cargo-mutant to be installed: cargo install cargo-mutant
        - Automatically finds the Cargo project root from focal_file_path
        - Runs mutation testing only on the specified function
    """
    # Validate focal file exists
    focal_file = Path(focal_file_path)
    if not focal_file.exists():
        return False, {
            "mutation_score": 0.0,
            "killed_count": 0,
            "escaped_count": 0,
            "duplicated_count": 0,
            "skipped_count": 0,
            "total_count": 0,
            "error_message": f"Focal file not found: {focal_file_path}"
        }
    
    # Validate function name is reasonable
    if not focal_function_name or not focal_function_name.strip():
        return False, {
            "mutation_score": 0.0,
            "killed_count": 0,
            "escaped_count": 0,
            "duplicated_count": 0,
            "skipped_count": 0,
            "total_count": 0,
            "error_message": "Empty or invalid function name provided"
        }
    
    # Find Cargo project root
    project_root = get_project_dir(focal_file_path)
    if not project_root:
        return False, {
            "mutation_score": 0.0,
            "caught_count": 0,
            "missed_count": 0,
            "timeout_count": 0,
            "unviable_count": 0,
            "total_count": 0,
            "error_message": f"Could not find Cargo.toml for {focal_file_path}"
        }
    
    # Use absolute paths to avoid ambiguity
    project_root_abs = project_root.resolve()
    mutants_out_dir = project_root_abs / "mutants.out"
    outcomes_json = mutants_out_dir / "outcomes.json"
    
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
        # Prepare environment
        env = os.environ.copy()
        
        # Clean previous mutation results
        if mutants_out_dir.exists():
            import shutil
            shutil.rmtree(mutants_out_dir, ignore_errors=True)
        
        # Calculate relative path for focal file to avoid path issues
        ref_focal_file = "/".join(focal_file_path.split("/")[4:])

        # Run cargo mutants with JSON output
        # Use --re to match the function name more precisely
        # Pattern: match function definition (pub fn, fn) followed by function name
        command = [
            "cargo",
            "mutants",
            "--file", ref_focal_file,
            "--re", f"{focal_function_name}$",
            "--output", str(mutants_out_dir),
            "--timeout", str(timeout),
            "--no-times",  # Disable timing info for cleaner output
            "--no-shuffle",  # Deterministic order for debugging
            "--cargo-test-arg=--tests",
            "--cargo-test-arg=tests_xrepotest",
        ]
        
        mutation_result = subprocess.run(
            command,
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout * 2,  # Give extra time for cargo mutant itself
            env=env,
        )
        
        # cargo mutant returns non-zero if there are uncaught mutants
        # This is expected, so we don't check return code strictly
        
        # Check if outcomes.json was generated
        if not outcomes_json.exists():
            # Try to parse stdout for error information
            stderr_info = mutation_result.stderr if mutation_result.stderr else ""
            stdout_info = mutation_result.stdout if mutation_result.stdout else ""
            
            # Fallback: Try to parse stdout summary if JSON is missing
            # Example: "11 mutants tested: 11 caught"
            # Example: "15 mutants tested: 1 missed, 12 caught, 2 unviable"
            summary_match = re.search(r"(\d+) mutants tested: (.*)", stdout_info)
            if summary_match:
                details_str = summary_match.group(2)
                
                killed_count = 0
                escaped_count = 0
                skipped_count = 0
                duplicated_count = 0
                
                # Parse details
                # "1 missed, 12 caught, 2 unviable"
                parts = details_str.split(',')
                for part in parts:
                    part = part.strip()
                    if "caught" in part:
                        killed_count = int(part.split()[0])
                    elif "missed" in part:
                        escaped_count = int(part.split()[0])
                    elif "unviable" in part:
                        skipped_count = int(part.split()[0])
                    elif "timeout" in part:
                        duplicated_count = int(part.split()[0])
                
                total_tested = killed_count + escaped_count + duplicated_count
                total_count = total_tested + skipped_count
                
                if total_tested > 0:
                    mutation_score = killed_count / total_tested
                else:
                    mutation_score = 0.0
                
                result["mutation_score"] = round(mutation_score, 4)
                result["killed_count"] = killed_count
                result["escaped_count"] = escaped_count
                result["duplicated_count"] = duplicated_count
                result["skipped_count"] = skipped_count
                result["total_count"] = total_count
                
                return True, result

            # Provide detailed error message with debugging info
            result["error_message"] = f"Mutation outcomes file not found at {outcomes_json}"
            
            # Add specific error detection
            if "No mutants found" in stderr_info or "No mutants found" in stdout_info:
                result["error_message"] += "\n[Root Cause] No mutants found - check: 1) Function name matches exactly, 2) Function is in the specified file, 3) Function is not macro-generated"
            elif "cargo test failed" in stderr_info or "cargo test failed" in stdout_info:
                result["error_message"] += "\n[Root Cause] Baseline test compilation/execution failed - the test doesn't work without mutations"
            elif mutation_result.returncode != 0:
                result["error_message"] += f"\n[Root Cause] cargo-mutants exited with code {mutation_result.returncode}"
            
            if stderr_info:
                result["error_message"] += f"\nStderr: {stderr_info[:500]}"
            if stdout_info:
                result["error_message"] += f"\nStdout: {stdout_info[:500]}"
            return False, result
        
        # Read and parse outcomes.json
        with open(outcomes_json, 'r', encoding='utf-8') as f:
            outcomes_data = json.load(f)
        
        # Parse outcomes
        killed_count = 0  # caught in cargo-mutant
        escaped_count = 0  # missed in cargo-mutant
        duplicated_count = 0  # timeout in cargo-mutant (mapped to duplicated)
        skipped_count = 0  # unviable in cargo-mutant
        
        for outcome in outcomes_data:
            outcome_type = outcome.get("outcome", "")
            
            if outcome_type == "caught":
                killed_count += 1
            elif outcome_type == "missed":
                escaped_count += 1
            elif outcome_type == "timeout":
                duplicated_count += 1
            elif outcome_type == "unviable":
                skipped_count += 1
        
        # Calculate totals and mutation score (MSI format: 0.0 to 1.0)
        total_tested = killed_count + escaped_count + duplicated_count
        total_count = total_tested + skipped_count
        
        if total_tested > 0:
            mutation_score = killed_count / total_tested  # MSI as decimal (0.0 - 1.0)
        else:
            mutation_score = 0.0
        
        result["mutation_score"] = round(mutation_score, 4)
        result["killed_count"] = killed_count
        result["escaped_count"] = escaped_count
        result["duplicated_count"] = duplicated_count
        result["skipped_count"] = skipped_count
        result["total_count"] = total_count
        
        # Validate that we found mutants
        if total_count == 0:
            result["error_message"] = "No mutants were generated. Check if the function exists and is testable."
            return False, result
        
        # Cleanup mutants.out directory (optional)
        try:
            if mutants_out_dir.exists():
                shutil.rmtree(mutants_out_dir, ignore_errors=True)
        except Exception as e:
            # Don't fail if cleanup fails
            print(f"Warning: Could not delete mutants output directory: {e}")
        
        return True, result
        
    except subprocess.TimeoutExpired:
        result["error_message"] = f"Mutation testing timeout (exceeded {timeout * 2} seconds)"
        return False, result
    except json.JSONDecodeError as e:
        result["error_message"] = f"Failed to parse mutation outcomes: {e}"
        # Try to read raw content for debugging
        try:
            with open(outcomes_json, 'r', encoding='utf-8') as f:
                raw_content = f.read()
            result["error_message"] += f"\nRaw content: {raw_content[:200]}"
        except Exception:
            pass
        return False, result
    except FileNotFoundError as e:
        result["error_message"] = f"File not found: {e}. Make sure cargo-mutant is installed."
        return False, result
    except PermissionError as e:
        result["error_message"] = f"Permission denied: {e}"
        return False, result
    except Exception as e:
        result["error_message"] = f"An unexpected error occurred: {type(e).__name__}: {e}"
        return False, result
