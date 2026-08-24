import re
from pathlib import Path
from tree_sitter import Language, Parser
import tree_sitter_php as ts_php
from typing import Tuple
import subprocess

from base.utils import find_descendants_by_type as find_descendants

PHP_LANGUAGE = Language(ts_php.language_php())
parser = Parser(PHP_LANGUAGE)


def create_php_file(file_path: str, function_name: str, test_code: str) -> str:
    """
    Create a PHP file with test code in the project's tests folder.
    Tests are already formatted with proper PHP tags and use statements.
    
    Args:
        file_path: Path to the source file
        function_name: Name of the function being tested
        test_code: Complete test code with PHP tags
    
    Returns:
        Path to the created test file
    """
    # Find project root by looking for composer.json
    current_dir = Path(file_path).parent
    project_root = current_dir
    
    # Search upward for composer.json to find project root
    while project_root.parent != project_root:
        if (project_root / "composer.json").exists():
            break
        project_root = project_root.parent
    
    # Create tests directory at project root
    tests_dir = project_root / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    fixed_test_code = (test_code or "").lstrip("\ufeff")

    # Ensure PHP open tag
    if "<?php" not in fixed_test_code:
        fixed_test_code = "<?php\n" + fixed_test_code

    # Remove any existing autoload requires
    fixed_test_code = re.sub(
        r"^\s*require(?:_once)?\b.*autoload\.php.*;\s*$",
        "",
        fixed_test_code,
        flags=re.MULTILINE,
    )

    # Remove non-compound use statements
    fixed_test_code = re.sub(
        r"^\s*use\s+[A-Za-z_][A-Za-z0-9_]*\s*;\s*$",
        "",
        fixed_test_code,
        flags=re.MULTILINE,
    )

    # Insert correct autoload require after <?php, optional declare(strict_types=1);, and optional namespace
    lines = fixed_test_code.splitlines()
    out_lines = []
    inserted = False
    i = 0
    while i < len(lines):
        line = lines[i]
        
        if not inserted and "<?php" in line:
            out_lines.append(line)
            j = i + 1
            
            # Skip empty lines
            while j < len(lines) and lines[j].strip() == "":
                out_lines.append(lines[j])
                j += 1
            
            # Check for declare(strict_types=1);
            if j < len(lines) and re.match(r"^\s*declare\s*\(\s*strict_types\s*=\s*1\s*\)\s*;", lines[j]):
                out_lines.append(lines[j])
                j += 1
                # Skip empty lines after declare
                while j < len(lines) and lines[j].strip() == "":
                    out_lines.append(lines[j])
                    j += 1
            
            # Check for namespace declaration
            if j < len(lines) and re.match(r"^\s*namespace\s+", lines[j]):
                out_lines.append(lines[j])
                j += 1
                # Skip empty lines after namespace
                while j < len(lines) and lines[j].strip() == "":
                    out_lines.append(lines[j])
                    j += 1
            
            # Insert require_once after namespace (or declare, or <?php)
            out_lines.append("require_once __DIR__ . '/../vendor/autoload.php';")
            inserted = True
            i = j  # Skip to the next unprocessed line
            continue
        
        out_lines.append(line)
        i += 1

    fixed_test_code = "\n".join(out_lines) + "\n"

    # Extract class name from the code
    m = re.search(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)\b", fixed_test_code)
    if not m:
        raise ValueError(f"No class declaration found in generated test code for {function_name}")
    
    class_name = m.group(1)

    # Name the file to match the class name
    test_file_path = tests_dir / f"{class_name}.php"

    with open(test_file_path, "w", encoding="utf-8") as f:
        f.write(fixed_test_code)

    return str(test_file_path)


def is_invoke_in_code(code, function_name):
    """
    Check if a function is invoked in the given PHP code.
    
    Args:
        code: PHP code as string
        function_name: Function name to check
    
    Returns:
        Boolean indicating if function is invoked
    """
    tree = parser.parse(bytes(code, "utf8"))
    
    # Find function call expressions
    call_nodes = find_descendants(tree.root_node, "function_call_expression")
    call_nodes.extend(find_descendants(tree.root_node, "member_call_expression"))
    call_nodes.extend(find_descendants(tree.root_node, "scoped_call_expression"))
    
    for call_node in call_nodes:
        identifiers = find_descendants(call_node, "name")
        for identifier in identifiers:
            if function_name == identifier.text.decode():
                return True
    
    return False
