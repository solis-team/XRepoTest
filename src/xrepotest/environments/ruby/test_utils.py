import re
from pathlib import Path
from tree_sitter import Language, Parser
import tree_sitter_ruby as ts_ruby
from typing import Tuple
import subprocess

from base.utils import find_descendants_by_type as find_descendants

RUBY_LANGUAGE = Language(ts_ruby.language())
parser = Parser(RUBY_LANGUAGE)


def create_ruby_file(file_path: str, function_name: str, test_code: str) -> str:
    """
    Create a Ruby file with test code in the project's spec folder.
    Tests are already formatted with proper require statements.
    
    Args:
        file_path: Path to the source file
        function_name: Name of the function being tested
        test_code: Complete test code with require statements
    
    Returns:
        Path to the created test file
    """
    # Find project root by looking for Gemfile
    current_dir = Path(file_path).parent
    project_root = current_dir
    
    # Search upward for Gemfile to find project root
    while project_root.parent != project_root:
        if (project_root / "Gemfile").exists():
            break
        project_root = project_root.parent
    
    # Create spec directory at project root (RSpec convention)
    spec_dir = project_root / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    
    # Clean up any existing temp test files
    for existing_test in spec_dir.glob("temp_*_spec.rb"):
        try:
            existing_test.unlink()
        except:
            pass

    test_file_name = "temp_spec.rb"
    test_file_path = spec_dir / test_file_name

    # Fix require paths if needed - tests in {project_root}/spec/ should use relative paths
    fixed_test_code = test_code
    
    # Remove any require_relative that goes too far up
    # RSpec tests typically use require 'lib/...' or require_relative '../lib/...'
    fixed_test_code = re.sub(
        r"require_relative\s+['\"](?:\.\./)+(?:\.\./)+",
        "require_relative '../",
        fixed_test_code
    )

    with open(test_file_path, "w", encoding="utf-8") as f:
        f.write(fixed_test_code)

    return str(test_file_path)


def is_invoke_in_code(code, function_name):
    """
    Check if a function is invoked in the given Ruby code.
    
    Args:
        code: Ruby code as string
        function_name: Function name to check
    
    Returns:
        Boolean indicating if function is invoked
    """
    tree = parser.parse(bytes(code, "utf8"))
    
    # Find method calls
    call_nodes = find_descendants(tree.root_node, "call")
    
    for call_node in call_nodes:
        identifiers = find_descendants(call_node, "identifier")
        identifiers.extend(find_descendants(call_node, "constant"))
        
        for identifier in identifiers:
            if function_name == identifier.text.decode():
                return True
    
    return False
