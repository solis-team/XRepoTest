import tree_sitter_julia as ts_julia
from tree_sitter import Language, Parser

from base.utils import find_descendants_by_type as find_descendants

JULIA_LANGUAGE = Language(ts_julia.language())
parser = Parser(JULIA_LANGUAGE)


def is_invoke_in_code(code, function_name):
    """Check if function is invoked in the code using AST"""
    tree = parser.parse(bytes(code, "utf8"))
    call_nodes = find_descendants(tree.root_node, "call")
    identifiers = []

    for call_node in call_nodes:
        identifier1 = find_descendants(
            call_node, "identifier")
        identifier2 = find_descendants(
            call_node, "field_expression")
        identifiers.extend(identifier1)
        identifiers.extend(identifier2)

    for identifier in identifiers:
        if function_name == identifier.text.decode():
            return True
    return False


def count_function_invocations(tests, focal_name) -> int:
    """
    Count how many tests invoke the focal function.
    Handles Julia-specific patterns like Base.function_name
    """
    # Handle Base.function_name pattern
    if "." in focal_name and focal_name.split(".")[0] == "Base":
        focal_name = focal_name.split(".")[-1]

    count = 0
    for test in tests:
        if is_invoke_in_code(test, focal_name):
            count += 1

    return count


def format_test_code(test_code: str, function_name: str) -> str:
    """
    Format Julia test code into a testset structure.
    
    Args:
        test_code: The test code string
        function_name: Name of the function being tested
    
    Returns:
        Formatted test code with testset wrapper if needed
    """
    # Wrap in testset if not already wrapped
    if not test_code.strip().startswith("@testset"):
        test_module = f"""
@testset "{function_name} Tests" begin
{test_code}
end
"""
        return test_module

    return test_code
