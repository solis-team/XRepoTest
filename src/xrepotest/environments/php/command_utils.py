import subprocess
import os
from pathlib import Path

from .coverage_utils import extract_line_cover_info


def get_package_dir(file_path: str):
    """Get the project root directory (where composer.json exists)."""
    current = Path(file_path).parent
    
    # Search upward for composer.json
    while current.parent != current:
        if (current / "composer.json").exists():
            return current.resolve()
        current = current.parent
    
    # Fallback to file's parent directory
    return Path(file_path).parent.resolve()


def check_compilation(test_file_path: str, test_code: str):
    """
    Check compilation of PHP test file using single php -r command.
    
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
        # Single command: load file và catch mọi lỗi compilation
        result = subprocess.run(
            ["php", "-l", str(test_file)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        # Nếu returncode = 0 nghĩa là compile thành công
        if result.returncode == 0:
            return True, "Compilation successful"
        else:
            # Lỗi compilation sẽ xuất hiện trong stderr
            error_output = result.stderr.strip() or result.stdout.strip()
            return False, f"Compilation error:\n{error_output}"
            
    except subprocess.TimeoutExpired:
        return False, "Compilation check timeout"
    except FileNotFoundError:
        return False, "PHP executable not found"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def check_test(test_file_path: str, test_code: str):
    """
    Run PHP tests using PHPUnit only.
    
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
    
    debug = os.environ.get("XREPOTEST_DEBUG_PHP", os.environ.get("TESSERA_DEBUG_PHP", "0")) == "1"

    # Use PHPUnit from vendor/bin (inside Docker container)
    phpunit_vendor = package_dir / "vendor" / "bin" / "phpunit"
    vendor_autoload = package_dir / "vendor" / "autoload.php"

    if debug:
        print(f"  Checking PHPUnit at: {phpunit_vendor}")
        print(f"  Package dir: {package_dir}")
        print(f"  PHPUnit exists: {phpunit_vendor.exists()}")
        print(f"  Vendor autoload exists: {vendor_autoload.exists()}")

    if not phpunit_vendor.exists():
        if vendor_autoload.exists():
            return False, f"PHPUnit binary not found at {phpunit_vendor} (but vendor/autoload.php exists)."
        return False, f"PHPUnit not found in {package_dir}/vendor/bin/. Please run 'composer install' in {package_dir}."

    # IMPORTANT: PHPUnit auto-detects phpunit.xml(.dist) in cwd and may run the repo's entire test suite.
    # To evaluate *only* the generated test file, run with a minimal temporary config.
    temp_config = package_dir / "phpunit.temp.test.xml"
    bootstrap_attr = f'bootstrap="{vendor_autoload}"' if vendor_autoload.exists() else ""
    config_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    config_content += f'<phpunit {bootstrap_attr}>\n'
    config_content += '    <testsuites>\n'
    config_content += '        <testsuite name="generated">\n'
    config_content += f'            <file>{test_file}</file>\n'
    config_content += '        </testsuite>\n'
    config_content += '    </testsuites>\n'
    config_content += '</phpunit>\n'
    temp_config.write_text(config_content)

    command = ["php", str(phpunit_vendor), "-c", str(temp_config)]
    
    try:
        result = subprocess.run(
            command,
            cwd=package_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        output = result.stdout + "\n" + result.stderr
        
        # PHPUnit returns 0 for passing tests
        if result.returncode == 0:
            return True, output.strip()
        else:
            return False, output.strip()
            
    except FileNotFoundError:
        return False, "PHPUnit not found. Tests must use PHPUnit framework."
    except subprocess.TimeoutExpired:
        return False, "Test execution timeout"
    except Exception as e:
        return False, f"An unexpected error occurred: {e}"
    finally:
        try:
            if temp_config.exists():
                temp_config.unlink()
        except Exception:
            pass


def generate_coverage_report(
    test_file_path: str,
    test_code: str,
    file_path: str, 
    start_line: int, 
    end_line: int
):
    """
    Generate coverage report for PHP tests using PHPUnit with code coverage.
    
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
    coverage_file = coverage_dir / "clover.xml"
    
    # Create coverage directory
    coverage_dir.mkdir(exist_ok=True)
    
    try:
        # Remove old clover file if exists
        if coverage_file.exists():
            coverage_file.unlink()
        
        # Create temporary phpunit config with filter for focal file
        temp_config = package_dir / 'phpunit.temp.xml'
        
        # Check if autoload file exists
        autoload_file = package_dir / 'vendor' / 'autoload.php'
        bootstrap_attr = f'bootstrap="{autoload_file}"' if autoload_file.exists() else ''
        
        config_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
        config_content += f'<phpunit {bootstrap_attr}>\n'
        config_content += '    <testsuites>\n'
        config_content += '        <testsuite name="test">\n'
        config_content += f'            <file>{test_file}</file>\n'
        config_content += '        </testsuite>\n'
        config_content += '    </testsuites>\n'
        
        # Add coverage filter for focal file
        if file_path:
            config_content += '    <coverage>\n'
            config_content += '        <include>\n'
            config_content += f'            <file>{file_path}</file>\n'
            config_content += '        </include>\n'
            config_content += '    </coverage>\n'
        
        config_content += '</phpunit>\n'
        
        # Write temporary config
        temp_config.write_text(config_content)
        
        # Try PHPUnit with coverage - prefer vendor installation
        phpunit_vendor = package_dir / "vendor" / "bin" / "phpunit"
        
        if phpunit_vendor.exists():
            command = [
                "php", "-d", "xdebug.mode=coverage",
                str(phpunit_vendor),
                "-c", "phpunit.temp.xml",
                "--coverage-clover", str(coverage_file)
            ]
        elif (package_dir / "vendor" / "autoload.php").exists():
            # Vendor exists, force use of vendor phpunit
            command = [
                "php", "-d", "xdebug.mode=coverage",
                str(phpunit_vendor),
                "-c", "phpunit.temp.xml",
                "--coverage-clover", str(coverage_file)
            ]
        else:
            # Try global phpunit
            command = [
                "php", "-d", "xdebug.mode=coverage",
                "vendor/bin/phpunit",
                "-c", "phpunit.temp.xml",
                "--coverage-clover", str(coverage_file)
            ]
        
        subprocess.run(
            command,
            cwd=package_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        
        # Clean up temporary config
        if temp_config.exists():
            temp_config.unlink()
        
        # Check if coverage file was generated
        if not coverage_file.exists():
            return False, "Coverage file not generated"
        
        # Parse coverage file
        with open(coverage_file, "r", encoding="utf-8") as f:
            coverage_data = f.read()
        
        # Extract coverage information
        summary = extract_line_cover_info(
            coverage_data,
            file_path,
            start_line,
            end_line,
        )
        
        return True, summary
        
    except subprocess.TimeoutExpired:
        return False, "Coverage generation timeout"
    except FileNotFoundError:
        return False, "PHPUnit not found or coverage driver not available"
    except Exception as e:
        return False, f"An unexpected error occurred: {e}"
    finally:
        # Clean up coverage directory
        try:
            if coverage_dir.exists():
                import shutil
                shutil.rmtree(coverage_dir)
        except:
            pass
