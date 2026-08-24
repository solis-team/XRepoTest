"""
Julia Test Evaluator

Handles Julia test execution and coverage measurement
"""

import subprocess
from pathlib import Path
from typing import Tuple, Optional

from experiments.standalone.evaluators.base_evaluator import LanguageEvaluator


class JuliaEvaluator(LanguageEvaluator):
    """Julia-specific test evaluator"""
    
    def __init__(self):
        super().__init__("Julia")
    
    def get_file_extension(self) -> str:
        return ".jl"
    
    def prepare_test_file(self, canonical_solution: str, test_code: str) -> str:
        """Prepare Julia test file"""
        return f"""
        # Canonical Solution
        {canonical_solution}

        # Generated Tests
        using Test
        {test_code}
        """
    
    def run_tests(self, focal_file_path: str, test_file_path: str) -> Tuple[bool, str, str]:
        """Run Julia tests"""
        import tempfile
        import os
        
        try:
            # Read test file content
            with open(test_file_path, 'r') as f:
                content = f.read()
            
            # Create temporary test file that includes the focal file
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.jl',
                delete=False
            ) as tmp_test:
                test_wrapper = f"""include("{os.path.abspath(focal_file_path)}")

                {content}
                """
                tmp_test.write(test_wrapper)
                tmp_test_path = tmp_test.name
            
            try:
                result = subprocess.run(
                    ['julia', tmp_test_path],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                success = result.returncode == 0
                return success, result.stdout, result.stderr
            finally:
                # Clean up temporary file
                try:
                    Path(tmp_test_path).unlink(missing_ok=True)
                except:
                    pass
                    
        except subprocess.TimeoutExpired:
            return False, "", "Test execution timed out"
        except Exception as e:
            return False, "", str(e)
    
    def measure_coverage(self, focal_file_path: str, test_file_path: str) -> Tuple[int, int]:
        """Measure Julia code coverage and return (covered_lines, total_lines)"""
        try:
            focal_path = Path(focal_file_path)
            test_path = Path(test_file_path)
            
            # Step 1: Count total executable lines by reading the focal file
            # Since Julia doesn't support empty test runs, count non-empty, non-comment lines
            total_lines = -1
            with open(focal_path, 'r') as f:
                for line in f:
                    stripped = line.strip()
                    # Skip empty lines, comment-only lines, and 'end' keywords
                    if stripped and not stripped.startswith('#') :
                        total_lines += 1
            
            print(f"Total executable lines in focal file: {total_lines}")
            
            # Step 2: Run tests with coverage to measure covered lines
            # Create a test file that includes the focal file
            test_with_include = test_path.parent / f"coverage_test_{test_path.name}"
            
            # Read the test file and extract just the test code (without canonical solution)
            test_content = test_path.read_text()
            if "# Generated Tests" in test_content:
                test_code = test_content.split("# Generated Tests")[1]
            else:
                test_code = test_content
            
            # Write test file that includes the focal file
            coverage_test_content = f"""include("{focal_path.absolute()}")

            using Test
            {test_code.replace("using Test", "").strip()}
            """
            test_with_include.write_text(coverage_test_content)
            print(focal_file_path, test_file_path, test_with_include)
            
            # Run tests with coverage
            result = subprocess.run(
                ['julia', '--code-coverage=user', test_with_include],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=test_path.parent
            )
            
            # Find .cov files that contain the focal file name
            focal_name = focal_path.stem  # Get filename without extension
            cov_files = [f for f in focal_path.parent.glob("*.cov") if focal_name in f.name]
            print("Coverage files found:", cov_files)
            
            covered_lines = 0
            if cov_files:
                cov_file = cov_files[0]  # Use the first matching file
                lines = cov_file.read_text().split('\n')
                
                for line in lines:
                    # Skip empty lines and comments
                    stripped = line.strip()
                    if not stripped or stripped.startswith('#'):
                        continue
                    
                    # Check if line has coverage info (starts with digits or dash after spaces)
                    parts = line.split(None, 1)
                    if len(parts) >= 2:
                        coverage_marker = parts[0]
                        # Count lines that were executed (have a number > 0)
                        if coverage_marker.isdigit() and int(coverage_marker) > 0:
                            covered_lines += 1
                
                # Clean up temporary files
                test_with_include.unlink(missing_ok=True)
                for cf in cov_files:
                    cf.unlink(missing_ok=True)
                
                print(f"Coverage: {covered_lines}/{total_lines} lines")
                return covered_lines, total_lines
            
            # Clean up even if no coverage file
            test_with_include.unlink(missing_ok=True)
            print(f"No coverage file found, returning 0/{total_lines}")
            return 0, total_lines
            
        except Exception as e:
            # Clean up on error
            print("Error during coverage measurement:", e)
            try:
                if 'test_with_include' in locals():
                    test_with_include.unlink(missing_ok=True)
                # Clean up any .cov files
                if 'focal_path' in locals():
                    for cf in focal_path.parent.glob("*.cov"):
                        cf.unlink(missing_ok=True)
            except:
                pass
            return 0, 0
