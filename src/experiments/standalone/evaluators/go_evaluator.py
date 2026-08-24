"""
Go Test Evaluator

Handles Go test execution and coverage measurement
"""

import subprocess
from typing import Tuple, Optional

from experiments.standalone.evaluators.base_evaluator import LanguageEvaluator


class GoEvaluator(LanguageEvaluator):
    """Go-specific test evaluator"""
    
    def __init__(self):
        super().__init__("Go")
    
    def get_file_extension(self) -> str:
        return ".go"
    
    def prepare_test_file(self, canonical_solution: str, test_code: str) -> str:
        """Prepare Go test file with proper structure"""
        import re
        
        # Extract imports from both canonical solution and test code
        imports = set()
        
        def extract_imports(code):
            # Match single import: import "fmt"
            single_imports = re.findall(r'^\s*import\s+"([^"]+)"', code, re.MULTILINE)
            imports.update(single_imports)
            
            # Match import blocks: import ( ... )
            import_blocks = re.findall(r'import\s*\(\s*([^)]+)\)', code, re.DOTALL)
            for block in import_blocks:
                block_imports = re.findall(r'"([^"]+)"', block)
                imports.update(block_imports)
        
        def remove_package_and_imports(code):
            # Remove package declarations
            code = re.sub(r'^\s*package\s+\w+\s*\n', '', code, flags=re.MULTILINE)
            # Remove import statements
            code = re.sub(r'^\s*import\s+"[^"]+"\s*\n', '', code, flags=re.MULTILINE)
            # Remove import blocks
            code = re.sub(r'import\s*\([^)]+\)\s*\n?', '', code, flags=re.DOTALL)
            return code.strip()
        
        # Extract imports from both parts
        extract_imports(canonical_solution)
        extract_imports(test_code)
        
        # Remove package and import statements from both
        clean_solution = remove_package_and_imports(canonical_solution)
        clean_test = remove_package_and_imports(test_code)
        
        # Build the file with proper structure
        result = "package main\n\n"
        
        # Add imports if any
        if imports:
            if len(imports) == 1:
                result += f'import "{list(imports)[0]}"\n\n'
            else:
                result += "import (\n"
                for imp in sorted(imports):
                    result += f'\t"{imp}"\n'
                result += ")\n\n"
        
        # Add canonical solution
        result += clean_solution + "\n\n"
        
        # Add test code
        result += clean_test + "\n"
        
        return result
    
    def compile_if_needed(self, test_file_path: str) -> Tuple[bool, str]:
        """Compile Go code"""
        try:
            result = subprocess.run(
                ['go', 'build', test_file_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                return False, result.stderr
            return True, ""
        except Exception as e:
            return False, str(e)
    

    def run_tests(self, focal_file_path: str, test_file_path: str):
        import tempfile
        from pathlib import Path
        import subprocess

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)

                # Read files
                with open(focal_file_path, "r") as f:
                    focal_code = f.read()

                with open(test_file_path, "r") as f:
                    test_code = f.read()

                # Merge focal + test code
                combined_code = self.prepare_test_file(focal_code, test_code)

                # Write combined Go file
                go_file = tmpdir_path / "main_test.go"
                go_file.write_text(combined_code)

                # Create go.mod
                with open(tmpdir_path / "go.mod", "w") as f:
                    f.write("module testmodule\n\ngo 1.21\n")

                    if "github.com/stretchr/testify" in combined_code:
                        f.write("require github.com/stretchr/testify v1.9.0\n")

                # Download deps if needed
                if "github.com/stretchr/testify" in combined_code:
                    subprocess.run(
                        ["go", "mod", "tidy"],
                        cwd=tmpdir_path,
                        timeout=60,
                        capture_output=True,
                        text=True
                    )

                # Run tests (IMPORTANT: no filename)
                result = subprocess.run(
                    ["go", "test", "-v"],
                    cwd=tmpdir_path,
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                return result.returncode == 0, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            return False, "", "Test execution timed out"
        except Exception as e:
            return False, "", str(e)

    def measure_coverage(self, focal_file_path: str, test_file_path: str):
        import tempfile
        from pathlib import Path
        import subprocess
        import re
        
        def strip_test_imports(code: str) -> str:
            TEST_IMPORTS = {
                "testing",
                "github.com/stretchr/testify/assert",
                "github.com/stretchr/testify/require",
            }

            lines = code.splitlines()
            output = []
            skip_block = False

            for line in lines:
                stripped = line.strip()

                if stripped.startswith("import ("):
                    skip_block = True
                    output.append(line)
                    continue

                if skip_block:
                    if stripped == ")":
                        skip_block = False
                        output.append(line)
                        continue
                    if any(t in stripped for t in TEST_IMPORTS):
                        continue
                    output.append(line)
                    continue

                if stripped.startswith("import"):
                    if any(t in stripped for t in TEST_IMPORTS):
                        continue

                output.append(line)

            return "\n".join(output)
        
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)

                # Read source files
                focal_code = Path(focal_file_path).read_text()
                test_code = Path(test_file_path).read_text()

                focal_code = strip_test_imports(focal_code)

                # Write focal code (NON-test file → coverage target)
                focal_go = tmpdir_path / "focal.go"
                focal_go.write_text(focal_code)

                # Create go.mod
                go_mod = tmpdir_path / "go.mod"
                go_mod.write_text(
                    "module testmodule\n\n"
                    "go 1.21\n"
                )

                # If testify is used, add dependency
                if "github.com/stretchr/testify" in test_code:
                    go_mod.write_text(
                        go_mod.read_text() +
                        "\nrequire github.com/stretchr/testify v1.9.0\n"
                    )

                    subprocess.run(
                        ["go", "mod", "tidy"],
                        cwd=tmpdir_path,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )

                # First, measure total lines with an empty test
                # IMPORTANT: Don't write focal_test.go yet - only focal.go + empty test
                empty_test_go = tmpdir_path / "empty_test.go"
                empty_test_go.write_text(
                    "package main\n\n"
                    "import \"testing\"\n\n"
                    "func TestEmpty(t *testing.T) {}\n"
                )
                
                # Get total statements from empty test coverage
                coverage_empty = tmpdir_path / "coverage_empty.out"
                result_empty = subprocess.run(
                    ["go", "test", f"-coverprofile={coverage_empty}"],
                    cwd=tmpdir_path,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                # print("Empty test run stdout:", result_empty)
                # print("Empty test coverage output:", result_empty.stdout)
                # Parse total statements from empty test
                total_statements = 0
                if coverage_empty.exists():
                    with open(coverage_empty, 'r') as f:
                        for line in f:
                            if line.startswith('mode:'):
                                continue
                            parts = line.strip().split()
                            if len(parts) >= 3:
                                try:
                                    total_statements += int(parts[1])
                                except (ValueError, IndexError):
                                    continue
                print(f"Total statements: {total_statements}")
                # Remove empty test file
                empty_test_go.unlink()
                coverage_empty.unlink(missing_ok=True)

                # NOW write the actual test file
                test_go = tmpdir_path / "focal_test.go"
                test_go.write_text(test_code)
                
                # Run go mod tidy again to ensure dependencies are loaded
                if "github.com/stretchr/testify" in test_code:
                    subprocess.run(
                        ["go", "mod", "tidy"],
                        cwd=tmpdir_path,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )

                # Run actual tests with coverage
                coverage_file = tmpdir_path / "coverage.out"
                result = subprocess.run(
                    ["go", "test", f"-coverprofile={coverage_file}"],
                    cwd=tmpdir_path,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                print("Actual test run stdout:", result)
                # Parse covered statements from actual test
                covered_statements = 0
                if coverage_file.exists():
                    with open(coverage_file, 'r') as f:
                        for line in f:
                            if line.startswith('mode:'):
                                continue
                            parts = line.strip().split()
                            if len(parts) >= 3:
                                try:
                                    num_statements = int(parts[1])
                                    execution_count = int(parts[2])
                                    if execution_count > 0:
                                        covered_statements += num_statements
                                except (ValueError, IndexError):
                                    continue
                
                if total_statements > 0:
                    print(f"Coverage: {covered_statements}/{total_statements} statements")
                    return covered_statements, total_statements
                
                # Fallback if coverage not available
                print("Coverage measurement failed - no statements found")
                return 0, 0

        except Exception as e:
            print("Coverage measurement failed:", e)
            return 0, 0
