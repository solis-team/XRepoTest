import re
from pathlib import Path
from tree_sitter import Language, Parser
import os
import tree_sitter_go as ts_go
from typing import Tuple
import subprocess

from base.utils import find_descendants_by_type as find_descendants

GO_LANGUAGE = Language(ts_go.language())
parser = Parser(GO_LANGUAGE)


def get_package_dir(file_path: str) -> Path:
    """
    Get the directory containing the file.
    """
    return Path(file_path).parent


def create_go_file(file_path: str, function_name: str, test_code: str) -> str:
    """
    Create a Go file with test code.
    Keeps the test in the same package as the source to allow access to private functions.
    """
    dir_path = os.path.dirname(file_path)

    # Delete all existing test files to avoid conflicts
    for existing_test in Path(dir_path).glob("*_test.go"):
        try:
            existing_test.unlink()
        except:
            pass

    test_file_name = "temp_test.go"
    test_file_path = os.path.join(dir_path, test_file_name)

    with open(test_file_path, "w") as f:
        f.write(test_code)

    return test_file_path


def extract_test_function_names(test_code: str) -> list:
    """
    Extract all test function names from Go test code.
    """
    tree = parser.parse(bytes(test_code, "utf8"))
    func_decls = find_descendants(tree.root_node, "function_declaration")
    test_names = []
    
    for node in func_decls:
        name_node = node.child_by_field_name("name")
        if name_node:
            name = name_node.text.decode("utf-8")
            if name.startswith("Test"):
                test_names.append(name)
                
    return test_names


def build_test_run_pattern(test_names: list) -> str:
    if not test_names:
        return ""
    joined = "|".join(test_names)
    return f"^({joined})$"


def is_invoke_in_code(code, function_name):
    tree = parser.parse(bytes(code, "utf8"))
    call_nodes = find_descendants(tree.root_node, "call")
    call_nodes.extend(
        find_descendants(
            tree.root_node,
            "invocation"))
    for call_node in call_nodes:
        # Match 'identifier', 'field_identifier', 'name', etc.
        identifiers = find_descendants(call_node, "ident")
        identifiers.extend(find_descendants(call_node, "name"))
        
        for identifier in identifiers:
            if function_name == identifier.text.decode():
                return True
    return False
