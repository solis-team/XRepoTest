from pathlib import Path
import re
from tree_sitter import Language, Parser
import tree_sitter_rust as ts_rust

from base.utils import find_descendants_by_type as find_descendants

RUST_LANGUAGE = Language(ts_rust.language())
parser = Parser(RUST_LANGUAGE)


def get_project_dir(file_path: str) -> Path:
    """
    Get the project directory from the file path.
    Assumes the structure is <repo_root>/src/...
    """
    path_str = str(file_path)
    if "/src/" in path_str:
        # Split at the last occurrence of /src/ to find the root
        parts = path_str.rsplit("/src/", 1)
        return Path(parts[0])
    return Path(file_path).parent


def format_test_code(test_module: str) -> str:
    """
    Format the test module by renaming it to 'tests_xrepotest' 
    so we can use a predictable cargo test filter.
    """
    # Rename 'mod tests', 'mod test', or any 'mod tests_...' to 'mod tests_xrepotest'
    renamed_module = re.sub(
        r'mod\s+(tests?|tests?_[\w\d_]+)\b',
        'mod tests_xrepotest',
        test_module,
        flags=re.IGNORECASE,
        count=1
    )
    return renamed_module


def create_rust_file(file_path: str, file_content: str, test_module: str) -> str:
    """
    Create a Rust test file with the given content and test module.
    """
    test_code = format_test_code(test_module)
    with open(Path(file_path), "w") as f:
        f.write(file_content + "\n\n" + test_code)
    return file_path


def return_file(file_path, code):
    with open(file_path, "w") as f:
        f.write(code)


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


def count_function_invocations(tests, focal_name) -> int:
    count = 0
    for test in tests:
        if is_invoke_in_code(test, focal_name):
            count += 1

    return count
