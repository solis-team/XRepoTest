"""
Rust Test Evaluator

Handles Rust test execution and coverage measurement using tarpaulin
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

from experiments.standalone.evaluators.base_evaluator import LanguageEvaluator

env = os.environ.copy()
env["RUSTFLAGS"] = "-Awarnings"

class RustEvaluator(LanguageEvaluator):
    """Rust-specific test evaluator"""
    
    def __init__(self):
        super().__init__("Rust")
    
    def get_file_extension(self) -> str:
        return ".rs"
    
    def get_project_dir(self, file_path: str) -> Path:
        """Get the project directory from the file path."""
        split_path = file_path.split("/src")
        return Path("".join(split_path[:-1]))
    
    def build_command(self, file_path: str, test_name: str) -> str:
        """Build the full test command path"""
        rel_path = file_path.split("/src/")[-1]
        module_path = rel_path.replace(".rs", "").replace("/", "::")
        test_full = f"{module_path}::tests_xrepotest"
        return test_full
    
    def process_coverage(self, sample: Dict[str, Any], coverage_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process coverage data for a given sample"""
        # Extract coverage statistics from llvm-cov JSON output
        coverage_stats = {
            "line_coverage": 0.0,
            "branch_coverage": 0.0,
            "region_coverage": 0.0
        }
        
        try:
            if 'data' in coverage_data and len(coverage_data['data']) > 0:
                totals = coverage_data['data'][0].get('totals', {})
                
                # Line coverage
                lines = totals.get('lines', {})
                if 'percent' in lines:
                    coverage_stats['line_coverage'] = lines['percent']
                
                # Branch coverage
                branches = totals.get('branches', {})
                if 'percent' in branches:
                    coverage_stats['branch_coverage'] = branches['percent']
                
                # Region coverage
                regions = totals.get('regions', {})
                if 'percent' in regions:
                    coverage_stats['region_coverage'] = regions['percent']
        except (KeyError, IndexError, TypeError):
            pass
        
        return coverage_stats
    
    def prepare_test_file(self, canonical_solution: str, test_code: str) -> str:
        """Prepare Rust test file"""
        return f"""{canonical_solution}

        {test_code}
        """
    
    def _clean_test_content(self, test_content: str) -> str:
        """Remove module wrappers and imports from test content"""
        import re
        
        lines = test_content.split('\n')
        cleaned_lines = []
        in_test_mod = False
        brace_count = 0
        skip_mod_declaration = False
        
        for line in lines:
            stripped = line.strip()
            
            # Skip 'use super::*;' or similar imports
            if stripped.startswith('use super::') or stripped.startswith('use crate::'):
                continue
            
            # Detect module declaration like 'mod tests {' or '#[cfg(test)] mod tests {'
            if re.match(r'^#?\[cfg\(test\)\]\s*$', stripped):
                skip_mod_declaration = True
                continue
            
            if skip_mod_declaration and stripped.startswith('mod ') and '{' in stripped:
                in_test_mod = True
                brace_count = stripped.count('{') - stripped.count('}')
                skip_mod_declaration = False
                continue
            
            if stripped.startswith('mod ') and '{' in stripped:
                in_test_mod = True
                brace_count = stripped.count('{') - stripped.count('}')
                continue
            
            # Track brace count to find end of module
            if in_test_mod:
                brace_count += line.count('{') - line.count('}')
                
                # If this line only contains the closing brace of the module, skip it
                if brace_count == 0 and stripped == '}':
                    in_test_mod = False
                    continue
                
                # Add line with reduced indentation (remove one level)
                if line.startswith('    '):
                    cleaned_lines.append(line[4:])
                else:
                    cleaned_lines.append(line)
            else:
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def compile_if_needed(self, test_file_path: str) -> Tuple[bool, str]:
        """Compile Rust code"""
        try:
            result = subprocess.run(
                ['rustc', '--test', test_file_path, '-o', test_file_path + '.out'],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                return False, result.stderr
            return True, ""
        except Exception as e:
            return False, str(e)
    
    def run_tests(self, focal_file_path: str, test_file_path: str) -> Tuple[bool, str, str]:
        """Run Rust tests by combining focal code and test code"""
        import tempfile
        import json
        try:
            # Read focal code
            with open(focal_file_path, 'r') as f:
                focal_code = f.read()
            
            # Read and clean test code
            with open(test_file_path, 'r') as f:
                test_code = f.read()
            
            # Clean test content (remove module wrappers and imports)
            test_code = self._clean_test_content(test_code)
            
            # Create temporary directory with cargo project
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                
                # Create minimal Cargo.toml
                cargo_toml = tmpdir_path / "Cargo.toml"
                with open(cargo_toml, 'w') as f:
                    f.write('[package]\n')
                    f.write('name = "test_runner"\n')
                    f.write('version = "0.1.0"\n')
                    f.write('edition = "2021"\n')
                    f.write('\n[dependencies]\n')
                    f.write('rand = "0.8"\n')
                    f.write('regex = "1.10"\n')
                    f.write('md5 = "0.7"\n')
                
                # Create src directory
                src_dir = tmpdir_path / "src"
                src_dir.mkdir()
                
                # Write combined code to src/lib.rs
                lib_file = src_dir / "lib.rs"
                with open(lib_file, 'w') as f:
                    f.write(focal_code)
                    f.write('\n\n')
                    f.write(test_code)
                
                # Run cargo test
                result = subprocess.run(
                    ['cargo', 'test', '--', '--nocapture'],
                    cwd=tmpdir_path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                success = result.returncode == 0
                return success, result.stdout, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "", "Test execution timed out"
        except Exception as e:
            return False, "", str(e)
    
    def measure_coverage(self, focal_file_path: str, test_file_path: str) -> Tuple[int, int]:
        """Measure Rust code coverage using cargo llvm-cov
        
        Returns:
            Tuple[int, int]: (covered_lines, total_lines)
        """
        import tempfile
        import json
        import re
        from collections import defaultdict
        
        try:
            # Read focal and test code
            with open(focal_file_path, 'r') as f:
                focal_code = f.read()
            
            with open(test_file_path, 'r') as f:
                test_code = f.read()
            
            # Clean test content
            test_code = self._clean_test_content(test_code)
            
            # Determine start and end line of focal function in combined file
            focal_lines = focal_code.split('\n')
            start_line, end_line = self._find_focal_function_range(focal_lines)
            
            if start_line is None or end_line is None:
                print("Could not determine focal function range")
                return 0, 0
            
            print(f"Focal function range: lines {start_line}-{end_line}")
            
            # Create temporary directory for coverage
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                
                # Create minimal Cargo.toml
                cargo_toml = tmpdir_path / "Cargo.toml"
                with open(cargo_toml, 'w') as f:
                    f.write('[package]\n')
                    f.write('name = "test_runner"\n')
                    f.write('version = "0.1.0"\n')
                    f.write('edition = "2021"\n')
                    f.write('\n[dependencies]\n')
                    f.write('rand = "0.8"\n')
                    f.write('regex = "1.10"\n')
                    f.write('md5 = "0.7"\n')
                
                # Create src directory
                src_dir = tmpdir_path / "src"
                src_dir.mkdir()
                
                # Step 1: Run with empty test to get total lines
                lib_file = src_dir / "lib.rs"
                empty_test = """
#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_empty() {
        assert!(true);
    }
}
"""
                with open(lib_file, 'w') as f:
                    f.write(focal_code)
                    f.write('\n\n')
                    f.write(empty_test)
                
                # Run empty test to get total lines
                result_empty = subprocess.run(
                    ['cargo', 'llvm-cov', '--json', '--ignore-run-fail', 'test'],
                    cwd=tmpdir_path,
                    capture_output=True,
                    text=True,
                    timeout=40
                )
                
                # Extract total lines from empty test
                _, total_lines = self._compute_focal_coverage(
                    result_empty.stdout, start_line, end_line
                )
                print(f"Total lines in focal function: {total_lines}")
                
                if total_lines == 0:
                    print("Could not determine total lines")
                    return 0, 0
                
                # Step 2: Run with actual test code
                with open(lib_file, 'w') as f:
                    f.write(focal_code)
                    f.write('\n\n')
                    f.write(test_code)
                
                # Run cargo llvm-cov with JSON output
                result = subprocess.run(
                    ['cargo', 'llvm-cov', '--json', '--ignore-run-fail', 'test'],
                    cwd=tmpdir_path,
                    capture_output=True,
                    text=True,
                    timeout=40
                )
                
                # Debug output
                with open("debug_coverage_file.json", "w") as debug_file:
                    debug_file.write(result.stdout)
                
                # Parse coverage data using segments
                covered_lines, _ = self._compute_focal_coverage(
                    result.stdout, start_line, end_line
                )
                
                print(f"Coverage: {covered_lines}/{total_lines} lines")
                return covered_lines, total_lines
                
        except subprocess.TimeoutExpired:
            print("Coverage measurement timed out")
            return 0, 0
        except Exception as e:
            print(f"Coverage measurement error: {e}")
            return 0, 0
    
    def _find_focal_function_range(self, focal_lines: list) -> Tuple[Optional[int], Optional[int]]:
        """Find the start and end line of the main focal function
        
        Returns:
            Tuple[Optional[int], Optional[int]]: (start_line, end_line) 1-indexed
        """
        import re
        
        # Look for function definitions (pub fn, fn, etc.)
        # Skip test functions and helper functions if possible
        start_line = None
        brace_count = 0
        in_function = False
        
        for i, line in enumerate(focal_lines, start=1):
            stripped = line.strip()
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith('//') or stripped.startswith('/*'):
                continue
            
            # Look for function definition (not in test module)
            if re.match(r'^(pub\s+)?fn\s+\w+', stripped):
                # Skip test functions
                if '#[test]' in focal_lines[max(0, i-2):i]:
                    continue
                
                if start_line is None:
                    start_line = i
                    in_function = True
            
            # Count braces to find function end
            if in_function:
                brace_count += line.count('{') - line.count('}')
                if brace_count == 0 and '{' in ''.join(focal_lines[start_line-1:i]):
                    # Function ended
                    return start_line, i
        
        # If we found a start but no end, return the last line
        if start_line is not None:
            return start_line, len(focal_lines)
        
        # Fallback: use all focal code
        return 1, len(focal_lines)
    
    def _compute_focal_coverage(self, coverage_json: str, start_line: int, end_line: int) -> Tuple[int, int]:
        """Compute coverage for focal function using segments
        
        Args:
            coverage_json: JSON output from llvm-cov
            start_line: Start line of focal function (1-indexed)
            end_line: End line of focal function (1-indexed)
        
        Returns:
            Tuple[int, int]: (covered_lines, total_lines)
        """
        from collections import defaultdict
        
        try:
            coverage_data = json.loads(coverage_json)
            
            # Find the lib.rs file in coverage data
            lib_file = None
            for file_data in coverage_data.get('data', [{}])[0].get('files', []):
                if 'lib.rs' in file_data.get('filename', ''):
                    lib_file = file_data
                    break
            
            if lib_file is None:
                print("Could not find lib.rs in coverage data")
                return 0, 0
            
            total_lines = set()
            covered_lines = set()
            
            # Process segments (line execution data)
            for segment in lib_file.get('segments', []):
                line = segment[0]  # line number (1-indexed)
                col = segment[1]   # column number
                count = segment[2]  # execution count
                
                # Filter lines within focal function range
                if line < start_line or line > end_line:
                    continue
                
                total_lines.add(line)
                if count > 0:
                    covered_lines.add(line)
            
            # Process branches within focal function
            branch_map = defaultdict(lambda: [0, 0])
            for branch in lib_file.get('branches', []):
                s_line, s_col, e_line, e_col = branch[:4]
                true_count = branch[4] if len(branch) > 4 else 0
                false_count = branch[5] if len(branch) > 5 else 0
                
                # Filter branches within focal function range
                if s_line < start_line or e_line > end_line:
                    continue
                
                pos = (s_line, s_col, e_line, e_col)
                branch_map[pos][0] += true_count
                branch_map[pos][1] += false_count
            
            print(f"Focal function coverage: {len(covered_lines)} covered, {len(total_lines)} total")
            print(f"Branch coverage points: {len(branch_map)}")
            
            return len(covered_lines), len(total_lines)
            
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"Failed to parse coverage data: {e}")
            return 0, 0
