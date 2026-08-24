"""
Ruby Test Evaluator

Handles Ruby test execution and coverage measurement using SimpleCov
"""

import subprocess
from pathlib import Path
from typing import Tuple, Optional

from experiments.standalone.evaluators.base_evaluator import LanguageEvaluator


class RubyEvaluator(LanguageEvaluator):
    """Ruby-specific test evaluator"""
    
    def __init__(self):
        super().__init__("Ruby")
    
    def get_file_extension(self) -> str:
        return ".rb"
    
    def prepare_test_file(self, canonical_solution: str, test_code: str) -> str:
        """Prepare Ruby test file with solution and tests"""
        return f"""# Canonical Solution
        {canonical_solution}

        # Generated Tests
        {test_code}
        """
    
    def run_tests(self, focal_file_path: str, test_file_path: str) -> Tuple[bool, str, str]:
        """Run Ruby tests using appropriate test framework"""
        import tempfile
        import os
        
        try:
            # Read test file content
            with open(test_file_path, 'r') as f:
                content = f.read()
            
            # Remove require_relative statements that try to load the solution/focal file
            lines = content.split('\n')
            filtered_lines = []
            for line in lines:
                # Skip lines that require the solution file
                if 'require_relative' in line and any(keyword in line.lower() for keyword in ['solution', 'focal', './solution', '../solution']):
                    continue
                # Skip require lines for the focal file
                if line.strip().startswith('require ') and any(keyword in line.lower() for keyword in ['solution', 'focal']):
                    continue
                filtered_lines.append(line)
            content = '\n'.join(filtered_lines)
            
            # Create temporary test file that requires the focal file
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.rb',
                delete=False
            ) as tmp_test:
                test_wrapper = f"""require '{os.path.abspath(focal_file_path)}'

{content}
"""
                tmp_test.write(test_wrapper)
                tmp_test_path = tmp_test.name
            
            try:
                # Detect if it's RSpec or Minitest
                if 'RSpec' in content or "require 'rspec'" in content:
                    # Use rspec command for RSpec tests
                    result = subprocess.run(
                        ['rspec', tmp_test_path, '--format', 'documentation'],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                else:
                    # Use ruby command for Minitest or other tests
                    result = subprocess.run(
                        ['ruby', tmp_test_path],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                
                print("Ruby Test Output:", result)
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
        """Measure Ruby code coverage using SimpleCov
        
        Returns:
            Tuple[int, int]: (covered_lines, total_lines)
        """
        import tempfile
        import os
        import json
        
        focal_path = Path(focal_file_path).absolute()
        test_path = Path(test_file_path).absolute()
        
        # Read the test file content
        try:
            test_content = test_path.read_text()
            
            # Remove require_relative statements that try to load the solution/focal file
            lines = test_content.split('\n')
            filtered_lines = []
            for line in lines:
                # Skip lines that require the solution file
                if 'require_relative' in line:
                    continue
                # Skip require lines for the focal file
                if line.strip().startswith('require ') and any(keyword in line.lower() for keyword in ['solution', 'focal']):
                    continue
                filtered_lines.append(line)
            test_content = '\n'.join(filtered_lines)
            
        except Exception as e:
            print(f"Failed to read test file: {e}")
            return 0, 0
        
        # Create a temporary directory with proper structure (lib/ and test/)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            
            # Create lib/ directory for focal code
            lib_dir = temp_dir_path / "lib"
            lib_dir.mkdir(exist_ok=True)
            
            # Create test/ directory for test code
            test_dir = temp_dir_path / "test"
            test_dir.mkdir(exist_ok=True)
            
            # Create coverage/ directory for reports
            coverage_dir = temp_dir_path / "coverage"
            coverage_dir.mkdir(exist_ok=True)
            
            # Copy focal file to lib/focal.rb
            focal_in_lib = lib_dir / "focal.rb"
            focal_in_lib.write_text(focal_path.read_text())
            
            # Create Gemfile for dependencies
            gemfile_path = temp_dir_path / "Gemfile"
            gemfile_content = """source 'https://rubygems.org'

            gem 'simplecov', require: false
            gem 'minitest'
            """
            gemfile_path.write_text(gemfile_content)
            
            # Step 1: Run empty test to get total lines
            empty_test = test_dir / "test_empty.rb"
            empty_test_code = f"""require 'simplecov'
            SimpleCov.start do
            add_filter '/test/'
            coverage_dir '{coverage_dir}'
            command_name 'EmptyTest'
            end

            require 'minitest/autorun'
            require_relative '../lib/focal'

            class TestEmpty < Minitest::Test
            def test_empty
                assert true
            end
            end
            """
            empty_test.write_text(empty_test_code)
            
            # Run empty test
            result_empty = subprocess.run(
                ['ruby', str(empty_test)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(temp_dir_path)
            )
            
            
            # Parse total lines from SimpleCov's output
            output_empty = result_empty.stdout + result_empty.stderr
            total_lines = 0
            
            # Extract from "Line Coverage: X.XX% (covered / total)" format
            for line in output_empty.split('\n'):
                if 'line coverage:' in line.lower() and '/' in line:
                    try:
                        # Extract the (covered / total) part
                        parts = line.split('(')[1].split(')')[0]
                        covered, total = parts.split('/')
                        total_lines = int(total.strip())
                        break
                    except Exception as e:
                        print(f"Failed to parse line: {line}, error: {e}")
            
            print(f"Total lines from empty test: {total_lines}")
            
            # Remove empty test files
            empty_test.unlink()
            
            # Step 2: Run actual test to get covered lines
            test_with_coverage = test_dir / "test_focal.rb"
            coverage_test_code = f"""require 'simplecov'
            SimpleCov.start do
            add_filter '/test/'
            coverage_dir '{coverage_dir}'
            command_name 'ActualTest'
            end

            require 'minitest/autorun'
            require_relative '../lib/focal'

            {test_content}
            """
            test_with_coverage.write_text(coverage_test_code)
            
            try:
                result = subprocess.run(
                    ['ruby', str(test_with_coverage)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=str(temp_dir_path)
                )
                
                # Parse covered lines from SimpleCov's output
                output = result.stdout + result.stderr
                covered_lines = 0
                
                # Extract from "Line Coverage: X.XX% (covered / total)" format
                for line in output.split('\n'):
                    if 'line coverage:' in line.lower() and '/' in line:
                        try:
                            # Extract the (covered / total) part
                            parts = line.split('(')[1].split(')')[0]
                            covered, total = parts.split('/')
                            covered_lines = int(covered.strip())
                            break
                        except Exception as e:
                            print(f"Failed to parse line: {line}, error: {e}")
                
                if total_lines > 0:
                    print(f"Coverage: {covered_lines}/{total_lines} lines")
                    return covered_lines, total_lines
                
                print("Coverage measurement failed - no lines found")
                return 0, 0
                
            except subprocess.TimeoutExpired:
                print("Coverage measurement timed out")
                return 0, 0
            except Exception as e:
                print(f"Coverage measurement error: {e}")
                return 0, 0
