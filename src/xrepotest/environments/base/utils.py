"""
Common utility functions for language environments.
"""

from typing import List, Any
from tree_sitter import Node

def find_descendants_by_type(node: Node, type_name: str) -> List[Node]:
    """
    Find all descendant nodes of a given type (non-strict matching).
    
    Args:
        node: Tree-sitter node to start search from
        type_name: Type name to search for (partial match)
        
    Returns:
        List of matching tree-sitter nodes
    """
    result = []
    if type_name in node.type:
        result.append(node)
    for child in node.children:
        result.extend(find_descendants_by_type(child, type_name))
    return result
