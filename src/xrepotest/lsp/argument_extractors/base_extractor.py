"""
Base class for language-specific argument extractors.

This module provides a common foundation for all argument extractors,
reducing code duplication and providing consistent interfaces.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from xrepotest.lsp.focal_method.token_classifier import TokenClassifier


class BaseArgumentExtractor(ABC):
    """
    Base class for language-specific argument extractors.
    
    Provides common functionality for:
    - Type classification and filtering
    - Parameter splitting with nested structure handling
    - Shared utilities for parsing function signatures
    
    Subclasses must implement:
    - get_language(): Return language identifier
    - extract_function_arguments(): Parse language-specific signatures
    - _parse_parameter(): Parse individual parameters
    - _extract_type_components(): Extract type names from complex types
    """
    
    def __init__(self, lsp_client=None):
        """
        Initialize the base extractor.
        
        Args:
            lsp_client: Optional LSP client for enhanced type resolution
        """
        self.lsp_client = lsp_client
        self._type_classifier = TokenClassifier(self.get_language())
        self.builtin_types = self._type_classifier.builtin_types
    
    @abstractmethod
    def get_language(self) -> str:
        """
        Return the language identifier.
        
        Returns:
            Language name (e.g., 'go', 'rust', 'ruby', 'php', 'julia')
        """
        pass
    
    @abstractmethod
    def extract_function_arguments(self, function_signature: str) -> List[Dict]:
        """
        Extract argument information from a function signature.
        
        Args:
            function_signature: The function signature string
            
        Returns:
            List of dictionaries containing argument information.
            Each dict should have at least:
            - 'name': argument name
            - 'type': type annotation (if available)
            - 'type_components': list of type names extracted
        """
        pass
    
    @abstractmethod
    def _parse_parameter(self, param: str) -> Optional[Dict]:
        """
        Parse a single parameter string into structured format.
        
        Args:
            param: Parameter string (e.g., "name: Type" or "Type name")
            
        Returns:
            Dictionary with parameter info or None if invalid
        """
        pass
    
    @abstractmethod
    def _extract_type_components(self, type_name: str) -> List[str]:
        """
        Extract all type names from a complex type expression.
        
        Handles language-specific type syntax:
        - Generics: List<T>, Vec<T>, HashMap<K,V>
        - References: &T, &mut T
        - Arrays: [T], []T, T[]
        - Unions: T | U, Union[T, U]
        - Functions: func(T) U, Fn(T) -> U
        
        Args:
            type_name: Type expression string
            
        Returns:
            List of individual type names found in the expression
        """
        pass
    
    def get_delimiters(self) -> str:
        """
        Return delimiters used for nested structure parsing.

        The order does not matter. Characters are interpreted by membership
        in the opening set ``([{<`` and closing set ``)]}>``.

        Returns:
            String containing delimiter characters to track
        """
        return "()[]{}<>"
    
    def _split_parameters(self, params_str: str, delimiters: Optional[str] = None) -> List[str]:
        """
        Split parameters by comma while respecting nested structures.
        
        Handles nested generics, arrays, tuples, etc. by tracking delimiter depth.
        
        Args:
            params_str: String containing comma-separated parameters
            delimiters: Optional delimiter pairs (uses get_delimiters() if not provided)
            
        Returns:
            List of parameter strings
            
        Example:
            "a, b: List<T, U>, c" -> ["a", "b: List<T, U>", "c"]
        """
        if delimiters is None:
            delimiters = self.get_delimiters()
        
        params = []
        current = []
        depth = 0
        
        opening = {char for char in delimiters if char in "([{<"}
        closing = {char for char in delimiters if char in ")]}>"}

        # Fallback to standard pairs if a subclass provides an empty/invalid set.
        if not opening or not closing:
            opening = set("([{<")
            closing = set(")]}>")
        
        for char in params_str:
            if char == ',' and depth == 0:
                if current:
                    params.append(''.join(current).strip())
                current = []
            else:
                if char in opening:
                    depth += 1
                elif char in closing:
                    if depth > 0:
                        depth -= 1
                current.append(char)
        
        if current:
            params.append(''.join(current).strip())
        
        return params
    
    def _is_builtin_type(self, type_name: str) -> bool:
        """
        Check if a type is a built-in language type.
        
        Args:
            type_name: Type name to check
            
        Returns:
            True if the type is a built-in type
        """
        return type_name in self.builtin_types
    
    def _normalize_whitespace(self, text: str) -> str:
        """
        Normalize whitespace in text.
        
        Args:
            text: Input text
            
        Returns:
            Text with normalized whitespace
        """
        return ' '.join(text.split())
