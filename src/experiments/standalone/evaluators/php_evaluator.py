"""
PHP Test Evaluator

Handles PHP test execution and coverage measurement using PHPUnit
"""

import subprocess
from typing import Tuple, Optional

from experiments.standalone.evaluators.base_evaluator import LanguageEvaluator


class PHPEvaluator(LanguageEvaluator):
    """PHP-specific test evaluator"""
    
    def __init__(self):
        super().__init__("PHP")
    
    def get_file_extension(self) -> str:
        return ".php"
    
    def _clean_test_content(self, test_file_path: str, focal_file_path: str) -> str:
        """
        Clean test content by removing PHP tags, replacing placeholder requires with actual focal file.
        
        Args:
            test_file_path: Path to the test file
            focal_file_path: Path to the focal file
            
        Returns:
            Cleaned test content as string
        """
        import re
        import os
        
        # Read the test file content
        with open(test_file_path, 'r') as f:
            test_content = f.read()
        
        # Clean the test content
        # Remove PHP tags
        test_content = test_content.replace('<?php', '').replace('?>', '').strip()
        
        # Replace any require/include statements with actual focal file path
        # This handles placeholders like: require_once 'your_code_file.php';
        focal_abs_path = os.path.abspath(focal_file_path)
        test_content = re.sub(
            r'^\s*(require_once|require|include_once|include)\s+[\'"].*?[\'"]\s*;',
            "\n",
            test_content,
            flags=re.MULTILINE
        )
        test_content = f'require_once \'{focal_abs_path}\';\n' + test_content
        
        # Read focal file to extract function names to avoid redeclaration
        with open(focal_file_path, 'r') as f:
            focal_content = f.read()
        
        # Extract function names from focal file
        focal_functions = set(re.findall(r'function\s+(\w+)\s*\(', focal_content))
        
        # Remove function declarations from test content that are already in focal file
        if focal_functions:
            lines = test_content.split('\n')
            cleaned_lines = []
            skip_until_brace_count = 0
            brace_count = 0
            
            for line in lines:
                # Check if this line declares a function that's in focal file
                func_match = re.search(r'function\s+(\w+)\s*\(', line)
                if func_match and func_match.group(1) in focal_functions and skip_until_brace_count == 0:
                    # Start skipping this function
                    skip_until_brace_count = 1
                    brace_count = line.count('{') - line.count('}')
                    continue
                
                if skip_until_brace_count > 0:
                    brace_count += line.count('{') - line.count('}')
                    if brace_count <= 0:
                        skip_until_brace_count = 0
                        brace_count = 0
                    continue
                
                cleaned_lines.append(line)
            
            test_content = '\n'.join(cleaned_lines)
        
        return test_content.strip()
    
    def prepare_test_file(self, canonical_solution: str, test_code: str) -> str:
        """Prepare PHP test file"""
        # Remove PHP tags if already present in canonical solution or test code
        clean_solution = canonical_solution.strip()
        if clean_solution.startswith('<?php'):
            clean_solution = clean_solution[5:].strip()
        if clean_solution.endswith('?>'):
            clean_solution = clean_solution[:-2].strip()
            
        clean_test = test_code.strip()
        if clean_test.startswith('<?php'):
            clean_test = clean_test[5:].strip()
        if clean_test.endswith('?>'):
            clean_test = clean_test[:-2].strip()
            
        return f"""<?php
        {clean_solution}

        {clean_test}
        """
    
    def run_tests(self, focal_file_path: str, test_file_path: str) -> Tuple[bool, str, str]:
        """Run PHP tests - uses PHPUnit if test class detected, otherwise plain php"""
        from pathlib import Path
        import tempfile
        import os
        
        try:
            # Clean test content (already includes require_once for focal file)
            test_content = self._clean_test_content(test_file_path, focal_file_path)
            
            # Check if this is a PHPUnit test class
            is_phpunit_test = 'TestCase' in test_content and 'class' in test_content
            
            # Create a temporary directory for test execution
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                
                # Create test file
                test_file = tmpdir_path / "test.php"
                test_wrapper = f"""<?php
{test_content}
"""
                with open(test_file, 'w') as f:
                    f.write(test_wrapper)
                
                if is_phpunit_test:
                    # Run with PHPUnit
                    # Try to find PHPUnit executable
                    phpunit_cmd = 'phpunit'
                    try:
                        which_result = subprocess.run(
                            ['which', 'phpunit'],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if which_result.returncode == 0:
                            phpunit_cmd = which_result.stdout.strip()
                    except:
                        pass
                    
                    # Create minimal phpunit.xml
                    phpunit_xml = tmpdir_path / "phpunit.xml"
                    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
                    <phpunit>
                        <testsuites>
                            <testsuite name="Test">
                                <file>{test_file}</file>
                            </testsuite>
                        </testsuites>
                    </phpunit>
                    """
                    with open(phpunit_xml, 'w') as f:
                        f.write(xml_content)
                    
                    result = subprocess.run(
                        ['php', phpunit_cmd, '-c', str(phpunit_xml)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        cwd=tmpdir_path
                    )
                else:
                    # Run with plain PHP
                    result = subprocess.run(
                        ['php', str(test_file)],
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
    
    def measure_coverage(self, focal_file_path: str, test_file_path: str) -> Optional[float]:
        """Measure PHP code coverage using PHPUnit with Xdebug (following reference implementation)"""
        from pathlib import Path
        import tempfile
        import os
        import xml.etree.ElementTree as ET
        
        try:
            # Clean test content (already includes require_once for focal file)
            test_content = self._clean_test_content(test_file_path, focal_file_path)
            
            # Create a temporary directory for PHPUnit configuration
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                
                # Create PHPUnit test file
                phpunit_test = tmpdir_path / "CoverageTest.php"
                with open(phpunit_test, 'w') as f:
                    f.write(f"<?php\n{test_content}\n")
                
                # Create coverage directory
                coverage_dir = tmpdir_path / "coverage"
                coverage_dir.mkdir(exist_ok=True)
                clover_file = coverage_dir / "clover.xml"
                
                # Create phpunit.xml configuration (following reference implementation)
                phpunit_xml = tmpdir_path / "phpunit.xml"
                xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
                <phpunit>
                    <testsuites>
                        <testsuite name="test">
                            <file>{phpunit_test}</file>
                        </testsuite>
                    </testsuites>
                    <coverage>
                        <include>
                            <file>{os.path.abspath(focal_file_path)}</file>
                        </include>
                    </coverage>
                </phpunit>
                """
                
                with open(phpunit_xml, 'w') as f:
                    f.write(xml_content)
                
                # Try to find PHPUnit executable (prefer vendor, then global)
                phpunit_cmd = 'phpunit'
                try:
                    which_result = subprocess.run(
                        ['which', 'phpunit'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if which_result.returncode == 0:
                        phpunit_cmd = which_result.stdout.strip()
                except:
                    pass
                
                # Run PHPUnit with coverage (following reference implementation)
                command = [
                    'php', '-d', 'xdebug.mode=coverage',
                    phpunit_cmd,
                    '-c', str(phpunit_xml),
                    '--coverage-clover', str(clover_file)
                ]
                
                result = subprocess.run(
                    command,
                    cwd=tmpdir_path,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                # Check if clover file was generated
                if not clover_file.exists():
                    return 0, 0
                
                # Print clover.xml content for debugging
                print("=" * 80)
                print("CLOVER.XML CONTENT:")
                print("=" * 80)
                with open(clover_file, 'r') as f:
                    clover_content = f.read()
                    print(clover_content)
                print("=" * 80)
                
                # Parse clover.xml to extract coverage
                tree = ET.parse(clover_file)
                root = tree.getroot()
                
                # Debug: print all file elements found
                all_files = root.findall('.//file')
                print(f"Found {len(all_files)} file elements in clover XML")
                for file_elem in all_files:
                    print(f"  File: {file_elem.get('name')}")
                
                # Find metrics for the focal file
                focal_abs_path = os.path.abspath(focal_file_path)
                print(f"Looking for focal file: {focal_abs_path}")
                
                for file_elem in root.findall('.//file'):
                    file_name = file_elem.get('name')
                    if file_name == focal_abs_path:
                        metrics = file_elem.find('metrics')
                        if metrics is not None:
                            statements = int(metrics.get('statements', 0))
                            covered_statements = int(metrics.get('coveredstatements', 0))
                            
                            print(f"Found coverage: {covered_statements}/{statements} statements covered")
                            
                            if statements > 0:
                                coverage_pct = (covered_statements / statements) * 100
                                return covered_statements, statements
                
                # Fallback: try to get project-level coverage
                print("Trying fallback: project-level coverage")
                project_metrics = root.find('.//metrics')
                if project_metrics is not None:
                    statements = int(project_metrics.get('statements', 0))
                    covered_statements = int(project_metrics.get('coveredstatements', 0))
                    
                    if statements > 0:
                        coverage_pct = (covered_statements / statements) * 100
                        return covered_statements, statements
                
                return covered_statements, statements
                
        except subprocess.TimeoutExpired:
            return 0,0
        except FileNotFoundError:
            print("PHPUnit or Xdebug not found")
            return 0,0
        except Exception as e:
            print(f"Coverage measurement error: {e}")
            return 0,0