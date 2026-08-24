import subprocess
import os
import json
from pathlib import Path


def get_package_dir(file_path: str):
    """Get the project root directory (where Gemfile exists)."""
    current = Path(file_path).parent
    
    # Search upward for Gemfile
    while current.parent != current:
        if (current / "Gemfile").exists():
            return current.resolve()
        current = current.parent
    
    # Fallback to file's parent directory
    return Path(file_path).parent.resolve()


def check_compilation(test_file_path: str, test_code: str):
    """
    Check compilation (syntax check) of Ruby test file using ruby -c.
    
    Args:
        test_file_path: Path to the test file
        test_code: Content of the test code
    
    Returns:
        Tuple of (success: bool, log: str)
    """
    test_file = Path(test_file_path)
    
    if not test_file.exists():
        return False, f"Test file not found: {test_file_path}"
    
    try:
        result = subprocess.run(
            ["ruby", "-c", str(test_file)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        output = result.stdout.strip() or result.stderr.strip()
        
        if result.returncode == 0:
            return True, output
        else:
            return False, output
            
    except subprocess.TimeoutExpired:
        return False, "Syntax check timeout"
    except FileNotFoundError:
        return False, "Ruby executable not found. Please install Ruby."
    except Exception as e:
        return False, f"An unexpected error occurred: {e}"


def check_test(test_file_path: str, test_code: str):
    """
    Run Ruby tests using RSpec with isolated configuration.
    
    Args:
        test_file_path: Path to the test file
        test_code: Content of the test code
    
    Returns:
        Tuple of (success: bool, log: str)
    """
    package_dir = get_package_dir(test_file_path)
    test_file = Path(test_file_path)
    
    if not test_file.exists():
        return False, f"Test file not found: {test_file_path}"
    
    # Run RSpec with bundle exec (standard Ruby practice)
    # Use --format progress for cleaner output
    command = ["bundle", "exec", "rspec", "--format", "progress", str(test_file)]
    
    try:
        result = subprocess.run(
            command,
            cwd=package_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        output = result.stdout + "\n" + result.stderr
        
        # RSpec returns 0 for passing tests
        if result.returncode == 0:
            return True, output.strip()
        else:
            return False, output.strip()
            
    except FileNotFoundError:
        # Try without bundle exec
        try:
            result = subprocess.run(
                ["rspec", str(test_file)],
                cwd=package_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            output = result.stdout + "\n" + result.stderr
            
            if result.returncode == 0:
                return True, output.strip()
            else:
                return False, output.strip()
        except FileNotFoundError:
            return False, "RSpec not found. Tests must use RSpec framework."
            
    except subprocess.TimeoutExpired:
        return False, "Test execution timeout"
    except Exception as e:
        return False, f"An unexpected error occurred: {e}"



def generate_coverage_report(
    test_file_path: str,
    test_code: str,
    file_path: str, 
    start_line: int, 
    end_line: int
):
    """
    Generate coverage report for Ruby tests using RSpec.
    
    Args:
        test_file_path: Path to the test file
        test_code: Content of the test code
        file_path: Path to the focal file
        start_line: Start line of the focal function
        end_line: End line of the focal function
    
    Returns:
        Tuple of (success: bool, coverage_data: dict)
    """
    package_dir = get_package_dir(test_file_path)
    test_file = Path(test_file_path)
    coverage_dir = package_dir / "coverage"
    
    # Create a temporary spec_helper to enable SimpleCov
    spec_helper_path = package_dir / "spec" / "spec_helper.rb"
    spec_helper_exists = spec_helper_path.exists()
    original_spec_helper = None
    
    try:
        # Backup original spec_helper if it exists
        if spec_helper_exists:
            with open(spec_helper_path, "r", encoding="utf-8") as f:
                original_spec_helper = f.read()
        
        # Create spec directory if it doesn't exist
        (package_dir / "spec").mkdir(exist_ok=True)
        
        # Write spec_helper with SimpleCov enabled
        with open(spec_helper_path, "w", encoding="utf-8") as f:
            f.write("require 'simplecov'\nSimpleCov.start\n")
            if original_spec_helper:
                f.write(original_spec_helper)
        
        # Calculate relative path from package_dir to focal file for require
        try:
            focal_relative = os.path.relpath(file_path, package_dir)
            # Remove .rb extension for require
            focal_require = focal_relative.replace('\\', '/').replace('.rb', '')
        except:
            focal_require = file_path.replace('.rb', '')
        
        # RSpec test with coverage wrapper
        wrapper = f"""
require 'coverage'
require 'json'
Coverage.start(lines: true)

# Explicitly load the focal file to ensure it's tracked by Coverage
begin
  require_relative '{focal_require}'
rescue LoadError => e
  # Try absolute path if relative doesn't work
  require '{file_path}'
end

require 'rspec/core'
RSpec::Core::Runner.run([ARGV[0]], $stderr, $stdout)

result = Coverage.result
STDERR.puts "COVERAGE_JSON_START"
STDERR.puts JSON.generate(result)
STDERR.puts "COVERAGE_JSON_END"
"""
        
        command = ["bundle", "exec", "ruby", "-I", "spec", "-I", "lib", "-e", wrapper, str(test_file)]
        
        result = subprocess.run(
            command,
            cwd=package_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        
        # Extract coverage data from stderr
        stderr = result.stderr
        
        if "COVERAGE_JSON_START" not in stderr or "COVERAGE_JSON_END" not in stderr:
            # Coverage markers not found - test might have failed or coverage didn't run
            return False, {
                "covered_lines": 0,
                "total_lines": 0,
                "coverage_percentage": 0.0
            }
        
        try:
            start_idx = stderr.index("COVERAGE_JSON_START") + len("COVERAGE_JSON_START\n")
            end_idx = stderr.index("COVERAGE_JSON_END")
            json_str = stderr[start_idx:end_idx].strip()
            coverage_data = json.loads(json_str)
            
            # Extract coverage for focal file - try multiple matching strategies
            focal_file_abs = str(Path(file_path).resolve())
            focal_file_name = Path(file_path).name
            
            covered_lines = 0
            total_lines = 0
            
            # Try to find the focal file in coverage data
            matched_file = None
            for file_key in coverage_data.keys():
                # Try exact match first
                if focal_file_abs == file_key or file_path == file_key:
                    matched_file = file_key
                    break
                # Try filename match
                if focal_file_name in file_key:
                    matched_file = file_key
                    break
                # Try relative path match
                if file_path.replace(os.sep, '/') in file_key.replace(os.sep, '/'):
                    matched_file = file_key
                    break
            
            if matched_file:
                line_coverage = coverage_data[matched_file]
                
                # Handle dict format (SimpleCov) vs array format (Coverage.result)
                if isinstance(line_coverage, dict) and 'lines' in line_coverage:
                    line_coverage = line_coverage['lines']
                
                if line_coverage and start_line and end_line:
                    # Count only lines in the focal function range
                    for line_num in range(start_line, end_line + 1):
                        line_idx = line_num - 1  # Convert to 0-indexed
                        if line_idx < len(line_coverage) and line_coverage[line_idx] is not None:
                            total_lines += 1
                            if line_coverage[line_idx] > 0:
                                covered_lines += 1
            
            coverage_percentage = (covered_lines / total_lines * 100) if total_lines > 0 else 0.0
            
            summary = {
                "covered_lines": covered_lines,
                "total_lines": total_lines,
                "coverage_percentage": coverage_percentage
            }
            
            return True, summary
        except (json.JSONDecodeError, KeyError, ValueError):
            return False, {
                "covered_lines": 0,
                "total_lines": 0,
                "coverage_percentage": 0.0
            }
        
    except subprocess.TimeoutExpired:
        return False, {
            "covered_lines": 0,
            "total_lines": 0,
            "coverage_percentage": 0.0
        }
    except FileNotFoundError:
        return False, {
            "covered_lines": 0,
            "total_lines": 0,
            "coverage_percentage": 0.0
        }
    except Exception as e:
        if os.environ.get("XREPOTEST_DEBUG_RUBY", os.environ.get("TESSERA_DEBUG_RUBY", "0")) == "1":
            print(f"  Exception in coverage generation: {e}")
        return False, {
            "covered_lines": 0,
            "total_lines": 0,
            "coverage_percentage": 0.0
        }
    finally:
        # Restore original spec_helper
        if spec_helper_exists and original_spec_helper is not None:
            try:
                with open(spec_helper_path, "w", encoding="utf-8") as f:
                    f.write(original_spec_helper)
            except:
                pass
        elif not spec_helper_exists and spec_helper_path.exists():
            try:
                spec_helper_path.unlink()
            except:
                pass
        
        # Clean up coverage directory
        try:
            if coverage_dir.exists():
                import shutil
                shutil.rmtree(coverage_dir)
        except:
            pass
