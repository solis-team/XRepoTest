"""
Language-agnostic utilities for CFG building.

Includes loop header extraction and other cross-language helpers.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Node


class LoopHeaderExtractor(ABC):
    """Extract loop header text for different languages"""
    
    @abstractmethod
    def extract_loop_header(self, node: 'Node') -> str:
        """Extract the loop initialization/condition text"""
        pass


class GoLoopHeaderExtractor(LoopHeaderExtractor):
    """Extract loop headers from Go for statements"""
    
    def extract_loop_header(self, node: 'Node') -> str:
        """Extract for loop header: 'for i := 0; i < n; i++' or 'for range'"""
        # Look for for_clause or range_clause children
        for child in node.children:
            if child.type == 'for_clause':
                # Classic for loop: init; condition; post
                return child.text.decode('utf8') if isinstance(child.text, bytes) else child.text
            elif child.type == 'range_clause':
                # Range-based for: for k, v := range collection
                return child.text.decode('utf8') if isinstance(child.text, bytes) else child.text
        
        # Fallback: just "for"
        return "for"


class PythonLoopHeaderExtractor(LoopHeaderExtractor):
    """Extract loop headers from Python for/while statements"""
    
    def extract_loop_header(self, node: 'Node') -> str:
        """Extract loop header: 'for x in iterable' or 'while condition'"""
        if node.type == 'for_statement':
            # Find 'left', 'in', 'right' pattern
            parts = []
            for child in node.children:
                if child.type in ['identifier', 'pattern_list', 'in', 'expression']:
                    text = child.text.decode('utf8') if isinstance(child.text, bytes) else child.text
                    parts.append(text)
                    if child.type == 'expression':
                        break  # Stop after right side of 'in'
            return ' '.join(parts) if parts else "for"
        
        elif node.type == 'while_statement':
            # Find condition
            for child in node.children:
                if child.type in ['comparison_operator', 'boolean_operator', 'identifier', 'call']:
                    text = child.text.decode('utf8') if isinstance(child.text, bytes) else child.text
                    return f"while {text}"
            return "while"
        
        return "loop"


class RustLoopHeaderExtractor(LoopHeaderExtractor):
    """Extract loop headers from Rust for/while expressions"""
    
    def extract_loop_header(self, node: 'Node') -> str:
        """Extract Rust loop header"""
        if node.type == 'for_expression':
            # for pattern in expression
            pattern = None
            expr = None
            for child in node.children:
                if child.type == 'identifier' and not pattern:
                    pattern = child.text.decode('utf8') if isinstance(child.text, bytes) else child.text
                elif child.type in ['call_expression', 'field_expression', 'identifier'] and pattern:
                    expr = child.text.decode('utf8') if isinstance(child.text, bytes) else child.text
                    break
            if pattern and expr:
                return f"for {pattern} in {expr}"
        
        elif node.type == 'while_expression':
            # while condition
            for child in node.children:
                if child.type in ['binary_expression', 'call_expression']:
                    cond = child.text.decode('utf8') if isinstance(child.text, bytes) else child.text
                    return f"while {cond}"
        
        return "loop"


class LoopHeaderExtractorFactory:
    """Factory to create language-specific loop header extractors"""
    
    @staticmethod
    def create_extractor(language: str) -> LoopHeaderExtractor:
        """Create appropriate extractor for the given language"""
        language = language.lower()
        
        if language == 'go':
            return GoLoopHeaderExtractor()
        elif language == 'python':
            return PythonLoopHeaderExtractor()
        elif language == 'rust':
            return RustLoopHeaderExtractor()
        else:
            # Default: generic extractor that just returns "loop"
            class GenericExtractor(LoopHeaderExtractor):
                def extract_loop_header(self, node):
                    return "loop"
            return GenericExtractor()
