"""
Token Extractor Module

Extract tokens from focal method body using tree-sitter.
Core component for LSPRAG-style context extraction.

This module provides:
- Tree-sitter-based AST parsing for multiple languages
- Identifier extraction from focal method bodies
- Token classification using parent-child AST relationships
- Language-specific node type analysis
"""

import logging
from typing import List, Dict, Any
from tree_sitter import Language, Parser, Node
import tree_sitter_go as tsgo
import tree_sitter_rust as tsrust
import tree_sitter_ruby as tsruby
import tree_sitter_php as tsphp
import tree_sitter_julia as tsjulia

from xrepotest.lsp.focal_method.token_classifier import TokenClassifier

logger = logging.getLogger(__name__)


class FocalMethodTokenExtractor:
    """
    Extract tokens from focal method body using tree-sitter.
    Core component for LSPRAG-style context extraction.
    """
    
    def __init__(self, language: str):
        self.language = language
        self.parser = self._init_parser()
        self.classifier = TokenClassifier(language)
        
    def _init_parser(self) -> Parser:
        """Initialize tree-sitter parser for language"""
        language_map = {
            'go': (tsgo, 'go'),
            'rust': (tsrust, 'rust'),
            'ruby': (tsruby, 'ruby'),
            'php': (tsphp, 'php'),
            'julia': (tsjulia, 'julia')
        }
        
        if self.language not in language_map:
            raise ValueError(f"Unsupported language: {self.language}")
        
        ts_module, lang_name = language_map[self.language]
        # PHP uses language_php() instead of language()
        if self.language == 'php':
            ts_language = Language(ts_module.language_php())
        else:
            ts_language = Language(ts_module.language())
        parser = Parser(ts_language)
        return parser
    
    def extract_tokens(self, focal_code: str, file_path: str, 
                      start_line: int = 0) -> List[Dict[str, Any]]:
        """
        Extract all identifiers from focal method code.
        
        Args:
            focal_code: The focal method source code
            file_path: Path to the source file
            start_line: Starting line number in the file
            
        Returns:
            List of token dictionaries with position info
        """
        # PHP requires <?php tag for parsing
        if self.language == 'php' and not focal_code.strip().startswith('<?php'):
            focal_code = '<?php\n' + focal_code
            start_line = max(0, start_line - 1)  # Adjust for added line
        
        # Parse the code
        tree = self.parser.parse(bytes(focal_code, 'utf-8'))
        
        # Extract tokens
        tokens = []
        self._traverse_tree(tree.root_node, tokens, start_line)
        
        # Filter and classify
        filtered_tokens = []
        for token in tokens:
            if not self.classifier.should_skip(token):
                token['need_definition'] = self.classifier.is_definition_helpful(token)
                token['need_references'] = self.classifier.is_reference_helpful(token)
                filtered_tokens.append(token)
        
        logger.debug(f"Extracted {len(filtered_tokens)} tokens from {len(tokens)} total")
        return filtered_tokens
    
    def _traverse_tree(self, node: Node, tokens: List[Dict], line_offset: int = 0):
        """Recursively traverse AST and extract identifier tokens"""
        # Token types we're interested in
        identifier_types = {
            'identifier', 'type_identifier', 'field_identifier',
            'function_identifier', 'method_identifier',
            'package_identifier', 'module_identifier',
            # PHP-specific
            'name', 'variable_name',
            # Ruby-specific  
            'constant', 'instance_variable', 'class_variable',
            # Julia-specific
            'field_expression'
        }
        
        if node.type in identifier_types:
            token_text = node.text.decode('utf-8') if node.text else ''
            if token_text:
                tokens.append({
                    'word': token_text,
                    'line': node.start_point[0] + line_offset,
                    'char': node.start_point[1],
                    'type': self._classify_node_type(node),
                    'is_assignment': self._is_assignment_target(node)
                })
        
        # Recurse to children
        for child in node.children:
            self._traverse_tree(child, tokens, line_offset)
    
    def _get_field_name(self, node: Node) -> str:
        """Get the field name for a node in its parent."""
        if not node.parent:
            return None
        try:
            child_index = node.parent.children.index(node)
            return node.parent.field_name_for_child(child_index)
        except (ValueError, AttributeError):
            return None
    
    def _classify_go_rust_node(self, node: Node, parent_type: str, field_name: str) -> str:
        """Classify nodes for Go and Rust languages.
        
        Both languages use similar patterns:
        - selector_expression (Go) / field_expression (Rust) for method calls and field access
        - call_expression for function calls
        """
        # Handle method calls and field access (e.g., obj.method(), obj.field)
        if parent_type in ['selector_expression', 'field_expression']:
            # Check if this is the field/method name (right side) vs package/object name (left side)
            # In Go: errors.New() -> 'errors' is left child (field), 'New' is right child (field='field')
            # In Rust: vec.push() -> 'vec' is left child, 'push' is right child (field='field')
            if field_name != 'field':
                # This is the left side (package name or object), not the method/field
                # Skip classification - package names should not be marked as functions
                return None
            
            # Check if parent is being called (grandparent is call_expression)
            if node.parent.parent and node.parent.parent.type in ['call_expression', 'method_call']:
                # This is a method name in a method call
                # e.g., fmt.Println() -> Println, vec.push() -> push
                return 'function'
            # Otherwise it's a regular field access (not a call)
            # e.g., obj.field, struct.member
            return 'field'
        
        # Handle scoped function calls (e.g., module::function)
        if parent_type in ['qualified_identifier', 'scoped_identifier']:
            # Check if this qualified name is being called
            if node.parent.parent and node.parent.parent.type in ['call_expression', 'function_call_expression']:
                return 'function'
        
        # Direct function calls
        if parent_type == 'call_expression' and field_name == 'function':
            return 'function'
        
        return None
    
    def _classify_julia_node(self, node: Node, parent_type: str, field_name: str) -> str:
        """Classify nodes for Julia language.
        
        Julia uses call_expression for function calls but doesn't assign field names.
        """
        # Handle method calls and field access
        if parent_type == 'field_expression':
            # Check if parent is being called
            if node.parent.parent and node.parent.parent.type == 'call_expression':
                return 'function'
            return 'field'
        
        # Julia doesn't assign field names, so check if it's the first child (function name)
        if parent_type == 'call_expression':
            if field_name is None:
                # In Julia, the function identifier is typically the first child
                if node.parent.children and node.parent.children[0] == node:
                    return 'function'
        
        return None
    
    def _classify_ruby_node(self, node: Node, parent_type: str, field_name: str) -> str:
        """Classify nodes for Ruby language.
        
        Ruby uses 'call' node for both method calls and field access.
        The difference is that method calls have argument_list or block children.
        """
        if parent_type == 'call' and field_name == 'method':
            # Check if parent has argument_list or block child (indicates method call)
            has_call_syntax = any(child.type in ['argument_list', 'block'] for child in node.parent.children)
            if not has_call_syntax:
                # This is field access, not a method call
                return 'field'
            return 'function'
        
        return None
    
    def _classify_php_node(self, node: Node, parent_type: str, field_name: str) -> str:
        """Classify nodes for PHP language.
        
        PHP distinguishes between:
        - member_call_expression: method calls like $obj->method()
        - member_access_expression: field access like $obj->field
        - scoped_call_expression: static method calls like Class::method()
        - function_call_expression: regular function calls
        """
        # Instance method calls
        if parent_type == 'member_call_expression' and field_name == 'name':
            return 'function'
        
        # Field access
        if parent_type == 'member_access_expression' and field_name == 'name':
            return 'field'
        
        # Static method calls (Class::method)
        if parent_type == 'scoped_call_expression' and field_name == 'name':
            return 'function'
        
        # Regular function calls
        if parent_type == 'function_call_expression' and field_name == 'function':
            return 'function'
        
        return None
    
    def _classify_type_nodes(self, node_type: str) -> str:
        """Classify type-related nodes across all languages."""
        # Go type nodes
        if node_type in [
            'type_identifier',           # Go/Rust: type names
            'qualified_type',            # Go: package.Type
            'generic_type',              # Go/Rust: Type[T] / Type<T>
            'pointer_type',              # Go/Rust: *Type
            'array_type',                # Go/Rust: [n]Type / [Type; n]
            'slice_type',                # Go: []Type
            'map_type',                  # Go: map[K]V
            'channel_type',              # Go: chan Type
            'struct_type',               # Go: struct {...}
            'interface_type',            # Go: interface {...}
            'reference_type',            # Rust: &Type, &mut Type
            'tuple_type',                # Rust: (T1, T2)
            'function_type',             # Rust: fn(args) -> return
            'named_type',                # PHP: class/interface names
            'union_type',                # PHP: Type1|Type2
            'intersection_type',         # PHP: Type1&Type2
            'optional_type',             # PHP: ?Type
            'primitive_type',            # PHP: int, string, etc.
            'parametrized_type',         # Julia: Type{T}
            'type_parameter_list',       # Julia: {T, S}
        ]:
            return 'type'
        
        return None
    
    def _classify_node_type(self, node: Node) -> str:
        """Classify node type for token classification.
        
        Delegates to language-specific classifiers for better organization.
        """
        node_type = node.type
        
        # Check parent context for better classification
        if node.parent:
            parent_type = node.parent.type
            field_name = self._get_field_name(node)
            
            # Try language-specific classifiers
            # Go and Rust share similar patterns
            result = self._classify_go_rust_node(node, parent_type, field_name)
            if result:
                return result
            
            # Julia-specific classification
            result = self._classify_julia_node(node, parent_type, field_name)
            if result:
                return result
            
            # Ruby-specific classification
            result = self._classify_ruby_node(node, parent_type, field_name)
            if result:
                return result
            
            # PHP-specific classification
            result = self._classify_php_node(node, parent_type, field_name)
            if result:
                return result
            
            # Generic classifications applicable to all languages
            if parent_type in ['call_expression', 'method_call'] and field_name in ['function', 'method', 'name']:
                return 'function'
            
            if parent_type in ['type', 'type_annotation', 'type_declaration']:
                return 'type'
            
            if parent_type in ['field_access']:
                return 'field'
            
            if parent_type in ['parameter_declaration', 'parameter']:
                return 'parameter'
        
        # Language-specific type node detection
        result = self._classify_type_nodes(node_type)
        if result:
            return result
        
        # Default classifications based on node type name
        if 'type' in node_type:
            return 'type'
        elif 'function' in node_type or 'method' in node_type:
            return 'function'
        elif 'field' in node_type:
            return 'field'
        else:
            return 'identifier'
    
    def _is_assignment_target(self, node: Node) -> bool:
        """Check if node is on left side of assignment"""
        if not node.parent:
            return False
        
        parent = node.parent
        assignment_types = {
            'assignment_statement', 'assignment_expression',
            'var_declaration', 'const_declaration', 'let_declaration',
            'short_var_declaration'
        }
        
        return parent.type in assignment_types
