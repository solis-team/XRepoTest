from tree_sitter import Language, Parser
import tree_sitter_go as ts_go
import tree_sitter_julia as ts_julia
import tree_sitter_rust as ts_rust

Julia_lang=Language(ts_julia.language())
julia_parser = Parser(Julia_lang)

Rust_lang=Language(ts_rust.language())
rust_parser = Parser(Rust_lang)

Go_lang=Language(ts_go.language())
go_parser = Parser(Go_lang)

from collections import deque
def get_child_node_by_name(node,node_name):
    q=deque([node])
    result=[]
    while q:
        curr=q.popleft()
        if curr.type==node_name:
            result.append(curr)
            continue
        for child in curr.children:
            q.append(child)
    return result
def get_next_child_node_by_name(node,node_name):
    result=[]
    for child in node.children:
        if child.type==node_name:
            result.append(child)
    return result

def delete_test_from_filecontext(parser, content) -> str:
    """Delete test-related code from file content.

    Deletes spans in reverse order (highest byte position first) to maintain
    validity of byte positions for subsequent deletions.
    """
    new_code = content

    # Step 1: Delete test modules
    tree = parser.parse(bytes(new_code, "utf8"))
    root = tree.root_node
    spans_to_delete = []

    mod_nodes = get_child_node_by_name(root, "mod_item")
    for mod_node in mod_nodes:
        identifiers = get_next_child_node_by_name(mod_node, "identifier")
        for identifier in identifiers:
            if "test" in identifier.text.decode("utf8"):
                spans_to_delete.append((mod_node.start_byte, mod_node.end_byte))
                break

    # Delete in reverse order to maintain byte position validity
    for start, end in sorted(spans_to_delete, key=lambda x: -x[0]):
        new_code = new_code[:start] + new_code[end:]

    # Step 2: Delete functions with assertions (re-parse with updated code)
    tree = parser.parse(bytes(new_code, "utf8"))
    root = tree.root_node
    spans_to_delete = []

    function_nodes = get_child_node_by_name(root, "function_item")
    for function in function_nodes:
        block_nodes = get_next_child_node_by_name(function, "block")
        if not block_nodes:
            continue
        block_node = block_nodes[0]
        if "assert" in block_node.text.decode("utf8"):
            spans_to_delete.append((function.start_byte, function.end_byte))

    # Delete in reverse order
    for start, end in sorted(spans_to_delete, key=lambda x: -x[0]):
        new_code = new_code[:start] + new_code[end:]

    # Step 3: Delete test attributes (re-parse with updated code)
    tree = parser.parse(bytes(new_code, "utf8"))
    root = tree.root_node
    spans_to_delete = []

    test_attributes = get_child_node_by_name(root, "attribute_item")
    for attribute in test_attributes:
        attr_text = attribute.text.decode()
        if attr_text == "#[test]" or attr_text == "#[cfg(test)]":
            spans_to_delete.append((attribute.start_byte, attribute.end_byte))

    # Delete in reverse order
    for start, end in sorted(spans_to_delete, key=lambda x: -x[0]):
        new_code = new_code[:start] + new_code[end:]

    # Step 4: Delete test-related comments (re-parse with updated code)
    tree = parser.parse(bytes(new_code, "utf8"))
    root = tree.root_node
    spans_to_delete = []

    comment_nodes = get_child_node_by_name(root, "line_comment")
    comment_nodes.extend(get_child_node_by_name(root, "block_comment"))
    for comment in comment_nodes:
        comment_text = comment.text.decode("utf8")
        if "test" in comment_text or "assert" in comment_text:
            spans_to_delete.append((comment.start_byte, comment.end_byte))

    # Delete in reverse order
    for start, end in sorted(spans_to_delete, key=lambda x: -x[0]):
        new_code = new_code[:start] + new_code[end:]

    return new_code
