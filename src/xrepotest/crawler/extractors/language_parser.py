#!/usr/bin/env python3
"""
Language Parser Module
Manages tree-sitter parsers for different languages
"""

from typing import Optional

from tree_sitter import Parser, Node, Language


class LanguageParser:
    """Manages tree-sitter parsers for different languages."""
    
    def __init__(self):
        self.parsers = {}
        self.languages = {}
        self._initialize_parsers()
    
    def _initialize_parsers(self):
        """Initialize tree-sitter parsers for all supported languages."""
        lang_configs = [
            ('go', 'tree_sitter_go'),
            ('rust', 'tree_sitter_rust'),
            ('julia', 'tree_sitter_julia'),
            ('ruby', 'tree_sitter_ruby'),
            ('php', 'tree_sitter_php')
        ]
        
        for lang_name, module_name in lang_configs:
            try:
                module = __import__(module_name)
                
                # Handle different module APIs
                if lang_name == 'php':
                    # PHP uses language_php() instead of language()
                    lang_obj = Language(module.language_php())
                else:
                    # Standard API
                    lang_obj = Language(module.language())
                
                # Create parser and set language
                parser = Parser()
                parser.language = lang_obj
                
                # Store both
                self.parsers[lang_name] = parser
                self.languages[lang_name] = lang_obj
                
                print(f"✓ Initialized {lang_name} parser")
            except Exception as e:
                print(f"✗ Failed to initialize {lang_name} parser: {e}")
    
    def parse(self, code: str, language: str) -> Optional[Node]:
        """Parse code and return AST root node."""
        lang_key = language.lower()
        if lang_key not in self.parsers:
            return None
        
        try:
            tree = self.parsers[lang_key].parse(bytes(code, 'utf8'))
            if tree is None:
                return None
            return tree.root_node
        except Exception as e:
            print(f"Error parsing {language} code: {e}")
            return None
