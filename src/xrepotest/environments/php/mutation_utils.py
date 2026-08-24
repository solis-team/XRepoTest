"""
Mutation testing utilities for PHP using Infection.
"""

import os
import shutil
import subprocess
import json
import tempfile
from pathlib import Path
from typing import Tuple, Dict, Any, Optional


def run_mutation_testing(
    test_file_path: str,
    focal_file_path: str,
    focal_function_name: str,
    project_root: str,
    timeout: int = 300,
    focal_start_line: Optional[int] = None,
    focal_end_line: Optional[int] = None,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Run mutation testing using Infection for PHP.
    
    Args:
        test_file_path: Path to the test file
        focal_file_path: Path to the focal file to mutate
        focal_function_name: Name of the function/method to filter by
        project_root: Root directory of the PHP project
        timeout: Timeout in seconds
        focal_start_line: First line of the focal function (1-based, inclusive)
        focal_end_line: Last line of the focal function (1-based, inclusive)
    
    Returns:
        Tuple[bool, Optional[Dict]]: (success, mutation_results)
        
    Example:
        success, results = run_mutation_testing(
            test_file_path='tests/MyTest.php',
            focal_file_path='src/MyClass.php',
            focal_function_name='myMethod',
            project_root='/path/to/project'
        )
    """
    package_dir = Path(project_root)
    # Prefer project-local Infection to avoid version conflicts with globally installed binary.
    # When a project ships its own vendor/bin/infection, using that binary ensures the correct
    # version is loaded and avoids PHP autoloader conflicts.
    _local_infection = package_dir / 'vendor' / 'bin' / 'infection'
    _global_infection = shutil.which("infection")
    infection_bin = _local_infection if _local_infection.exists() else (Path(_global_infection) if _global_infection else _local_infection)
    infection_log = package_dir / 'infection.json'
    infection_config = package_dir / 'infection_temp_config.json'
    vendor_autoload = package_dir / 'vendor' / 'autoload.php'
    phpunit_temp_dir = None  # Created inside try; isolated dir avoids duplicate --configuration flags
    phpunit_config = None   # Set after temp dir is created
    
    # Initialize result
    result_dict = {
        "mutation_score": 0.0,
        "killed_count": 0,
        "escaped_count": 0,
        "error_count": 0,
        "timeout_count": 0,
        "not_covered_count": 0,
        "total_count": 0,
        "error_message": ""
    }
    
    try:
        # Check if Infection exists
        if not infection_bin.exists():
            result_dict["error_message"] = "Infection not found. Install globally with: composer global require infection/infection"
            return False, result_dict
        
        # Create isolated temp directory; Infection discovers phpunit.xml via configDir,
        # so it never needs (and we never pass) an extra --configuration CLI flag.
        phpunit_temp_dir = tempfile.mkdtemp(prefix="xrepotest_phpunit_")
        phpunit_config = Path(phpunit_temp_dir) / "phpunit.xml"

        # Clean up old infection log and cached mutation data.
        # Infection 0.29.9 caches processed mutants in .infection/ inside the project.
        # After an OOM crash the cache is corrupt/empty, causing all subsequent runs
        # on the same file to return 0 mutants. Delete it before every run.
        if infection_log.exists():
            infection_log.unlink()
        infection_cache_dir = package_dir / '.infection'
        if infection_cache_dir.exists():
            shutil.rmtree(infection_cache_dir, ignore_errors=True)

        # Create temporary PHPUnit config to run only our specific test
        if test_file_path:
            test_file = Path(test_file_path)
            # Convert test file to relative path from project root
            test_rel = test_file.relative_to(package_dir) if test_file.is_absolute() else test_file
            
            bootstrap_attr = f'bootstrap="{vendor_autoload}"' if vendor_autoload.exists() else ""

            # Determine source directory for the <coverage> filter.
            # PHPUnit 10 exits 1 (OK-but-warnings) when no coverage filter is set,
            # which Infection treats as a hard test-suite failure.
            # Use the absolute path: Infection resolves paths in phpunit.xml
            # relative to configDir (our temp dir), so relative paths would
            # resolve to non-existent locations inside the temp dir.
            focal_source_dir = ""
            if focal_file_path:
                focal_source_dir = str(Path(focal_file_path).parent).replace("\\", "/")

            phpunit_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
            # executionOrder="default" suppresses Infection's "random order" warning.
            # failOnWarning/failOnRisky="false": PHPUnit 10 exits 1 for any warning
            # (risky tests, deprecations, etc.), which Infection treats as a hard
            # test-suite failure. These attributes prevent that.
            phpunit_content += (
                f'<phpunit {bootstrap_attr} executionOrder="default" '
                f'failOnWarning="false" failOnRisky="false">\n'
            )
            phpunit_content += '    <testsuites>\n'
            phpunit_content += '        <testsuite name="mutation">\n'
            # Use absolute path: with configDir set, PHPUnit resolves relative
            # paths from the temp dir, not the project root.
            phpunit_content += f'            <file>{test_file.resolve()}</file>\n'
            phpunit_content += '        </testsuite>\n'
            phpunit_content += '    </testsuites>\n'
            if focal_source_dir:
                # PHPUnit 10 uses <source> (not the old <coverage>) to declare
                # which files are included in coverage. Using the old <coverage>
                # with a nested <include> causes an XML validation error and
                # "No tests executed!" — which makes Infection treat exit 1 as failure.
                phpunit_content += '    <source>\n'
                phpunit_content += '        <include>\n'
                phpunit_content += f'            <directory suffix=".php">{focal_source_dir}</directory>\n'
                phpunit_content += '        </include>\n'
                phpunit_content += '    </source>\n'
            phpunit_content += '</phpunit>\n'
            phpunit_config.write_text(phpunit_content)

            print(f"[DEBUG] Created PHPUnit config: {phpunit_config}")
            print(f"[DEBUG] Test file in config: {test_rel}")
        
        # Create temporary configuration file
        # NOTE: Infection validates this file against its JSON schema.
        # Keep this minimal and pass runtime options via CLI flags.
        config_data = {
            "source": {
                "directories": ["."]
            },
            "logs": {
                "json": "infection.json"
            },
            "mutators": {
                "@default": True
            },
            # Tell Infection where our phpunit.xml lives so it discovers it natively.
            # This avoids us passing --test-framework-options=--configuration=..., which
            # would create a duplicate --configuration flag and cause PHPUnit 10 to exit 1.
            "phpUnit": {
                "configDir": phpunit_temp_dir
            },
        }
        
        with open(infection_config, 'w') as f:
            json.dump(config_data, f, indent=4)
        
        debug = os.environ.get("XREPOTEST_DEBUG_PHP", os.environ.get("TESSERA_DEBUG_PHP", "0")) == "1"

        # Invoke Infection via the PHP CLI so we can raise the memory limit.
        # CarbonPeriod.php and other large files generate thousands of mutants;
        # the default 512 MB limit is hit when JsonLogger serialises the result.
        cmd = [
            'php',
            '-d', 'memory_limit=2G',
            str(infection_bin),
            '--no-interaction',
            f'--configuration={infection_config.name}',
            '--test-framework=phpunit',
            '--threads=4',
            '--initial-tests-php-options=-d xdebug.mode=coverage',
            # Execute only the test cases that cover the mutated line, not the
            # whole test file. PHPUnit-only; uses --filter internally per mutant.
            # Pure performance win with no correctness tradeoff.
            '--only-covering-test-cases',
        ]

        if debug:
            cmd.append('--debug')
            # Surface mutation diffs in debug logs (default shows 20; max shows all).
            cmd.append('--show-mutations=50')
        
        # Add file filter for mutations
        if focal_file_path:
            focal_rel_path = Path(focal_file_path).relative_to(package_dir)
            cmd.append(f'--filter={focal_rel_path}')
        
        print(f"[DEBUG] Mutation command: {' '.join(cmd)}")
        print(f"[DEBUG] Working directory: {package_dir}")
        print(f"[DEBUG] Function: {focal_function_name}")
        
        # Run Infection
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(package_dir),
            timeout=timeout
        )
        
        # Clean up config files
        if infection_config.exists():
            infection_config.unlink()
        if phpunit_temp_dir:
            shutil.rmtree(phpunit_temp_dir, ignore_errors=True)
        
        # Parse infection.json
        if not infection_log.exists():
            result_dict["error_message"] = (
                "Infection log not generated. "
                f"Return code: {result.returncode}. "
                f"Stdout: {result.stdout[:4000]}, Stderr: {result.stderr[:4000]}"
            )
            return False, result_dict
        
        with open(infection_log, 'r') as f:
            data = json.load(f)
        
        # Filter mutants to those originating within the focal function's line range.
        # Infection records originalStartLine for every mutant, which is more reliable
        # than source.method (which may be null, qualified, or differently cased).
        # --filter=file.php already scopes Infection to the focal file; this narrows
        # further to the exact function.
        mutants = data.get('mutants', [])
        original_count = len(mutants)

        # Always log a sample of originalStartLine values so we can verify alignment.
        sample_lines = [m.get('originalStartLine') for m in mutants[:5]]
        print(f"[DEBUG] infection.json: {original_count} total mutants, "
              f"sample originalStartLine values: {sample_lines}")
        print(f"[DEBUG] Focal range: start={focal_start_line}, end={focal_end_line}")

        if focal_start_line is not None and focal_end_line is not None:
            filtered = [
                m for m in mutants
                if focal_start_line <= m.get('originalStartLine', -1) <= focal_end_line
            ]
            print(f"[DEBUG] Filtered {original_count} mutants down to {len(filtered)} "
                  f"for function '{focal_function_name}' (lines {focal_start_line}-{focal_end_line})")
            mutants = filtered
        elif focal_function_name and mutants:
            # Fallback when line range is unavailable: match source.method.
            # Infection writes it as "methodName" or "ClassName::methodName".
            focal_lower = focal_function_name.lower()
            suffix = f"::{focal_function_name}"
            suffix_lower = f"::{focal_lower}"
            filtered = [
                m for m in mutants
                if (
                    (m.get('source', {}).get('method') or '') == focal_function_name
                    or (m.get('source', {}).get('method') or '').endswith(suffix)
                    or (m.get('source', {}).get('method') or '').lower() == focal_lower
                    or (m.get('source', {}).get('method') or '').lower().endswith(suffix_lower)
                )
            ]
            if not filtered:
                seen_methods = sorted({
                    m.get('source', {}).get('method')
                    for m in mutants
                    if m.get('source', {}).get('method')
                })
                print(f"[DEBUG] No method match for '{focal_function_name}'. "
                      f"Available: {seen_methods}. Returning 0 mutants.")
            print(f"[DEBUG] Filtered {original_count} mutants down to {len(filtered)} "
                  f"for function '{focal_function_name}' (method-name match)")
            mutants = filtered
        
        # Calculate statistics
        total = len(mutants)
        killed = sum(1 for m in mutants if m['status'] in ['Killed', 'Timeout'])
        escaped = sum(1 for m in mutants if m['status'] == 'Escaped')
        errors = sum(1 for m in mutants if m['status'] == 'Error')
        not_covered = sum(1 for m in mutants if m['status'] == 'Not Covered')
        timeout_count = sum(1 for m in mutants if m['status'] == 'Timeout')
        
        # MSI calculation: (Killed + Timeout + Error) / (Total - Not Covered)
        covered_mutants = total - not_covered
        mutation_score = ((killed + errors) / covered_mutants) if covered_mutants > 0 else 0.0
        
        result_dict.update({
            "mutation_score": round(mutation_score, 2),
            "killed_count": killed,
            "escaped_count": escaped,
            "error_count": errors,
            "timeout_count": timeout_count,
            "not_covered_count": not_covered,
            "total_count": total
        })
        
        # Clean up infection log
        if infection_log.exists():
            infection_log.unlink()
        
        if total == 0:
            result_dict["error_message"] = "No mutants generated for the specified function"
            return False, result_dict
        
        return True, result_dict
        
    except subprocess.TimeoutExpired:
        result_dict["error_message"] = f"Mutation testing timeout (exceeded {timeout} seconds)"
        if infection_config.exists():
            infection_config.unlink()
        if infection_log.exists():
            infection_log.unlink()
        if phpunit_temp_dir:
            shutil.rmtree(phpunit_temp_dir, ignore_errors=True)
        return False, result_dict
    except json.JSONDecodeError as e:
        result_dict["error_message"] = f"Failed to parse infection.json: {e}"
        if infection_config.exists():
            infection_config.unlink()
        if phpunit_temp_dir:
            shutil.rmtree(phpunit_temp_dir, ignore_errors=True)
        return False, result_dict
    except FileNotFoundError as e:
        result_dict["error_message"] = f"File not found: {e}"
        if infection_config.exists():
            infection_config.unlink()
        if phpunit_temp_dir:
            shutil.rmtree(phpunit_temp_dir, ignore_errors=True)
        return False, result_dict
    except Exception as e:
        result_dict["error_message"] = f"Mutation testing error: {e}"
        if infection_config.exists():
            infection_config.unlink()
        if infection_log.exists():
            infection_log.unlink()
        if phpunit_temp_dir:
            shutil.rmtree(phpunit_temp_dir, ignore_errors=True)
        return False, result_dict
