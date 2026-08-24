#!/usr/bin/env python3
"""
Function Extractor Module
Extracts functions from AST nodes with language-specific handling
"""

import re
from pathlib import Path
from typing import List, Dict, Optional

from tree_sitter import Node

from xrepotest.crawler.default_config import load_crawler_config
from xrepotest.crawler.models import FunctionComponent, FunctionMetadata
from dataclasses import asdict


class FunctionExtractor:
    """Extracts functions from AST nodes with language-specific handling."""
    
    def __init__(self, language_parser, config_path: str = 'config.json'):
        self.parser = language_parser
        self.config = load_crawler_config(config_path)
        self.exclude_functions = self.config.get('exclude_functions', [])
        self.filter_rules = {
            lang.lower(): rules
            for lang, rules in self.config.get('filter_rules', {}).items()
        }
        self.repo_filter_rules = {
            lang.lower(): {
                repo_name.lower(): rules
                for repo_name, rules in repo_rules.items()
            }
            for lang, repo_rules in self.config.get('repo_filter_rules', {}).items()
            if isinstance(repo_rules, dict)
        }
    
    def count_lines(self, code: str) -> int:
        """Count non-empty, non-comment lines."""
        lines = code.split('\n')
        non_empty = [line for line in lines if line.strip() and not self._is_comment_line(line)]
        return len(non_empty)
    
    def _is_comment_line(self, line: str) -> bool:
        """Check if line is a comment."""
        stripped = line.strip()
        # Common comment patterns
        return (stripped.startswith('//') or 
                stripped.startswith('#') or 
                stripped.startswith('--') or
                stripped.startswith('/*') or
                stripped.startswith('*'))
    
    def has_return_statement(self, node: Node, language: str) -> bool:
        """Check if function has return statement via AST traversal."""
        lang_lower = language.lower()

        # Return statement node types per language
        return_types = {
            'go': ['return_statement'],
            'rust': ['return_expression'],
            'julia': ['return'],
            'ruby': ['return'],
            'php': ['return_statement'],
        }

        target_types = set(return_types.get(lang_lower, ['return_statement']))

        def traverse(n: Node) -> bool:
            if n.type in target_types:
                return True
            for child in n.children:
                if traverse(child):
                    return True
            return False

        return traverse(node)
    
    def get_node_text(self, node: Node, source_bytes: bytes) -> str:
        """Extract text from AST node."""
        return source_bytes[node.start_byte:node.end_byte].decode('utf8')
    
    def get_class_context(self, node: Node, source_bytes: bytes, language: str) -> Dict[str, str]:
        """Extract class/module context for a function."""
        context = {
            'wrap_class': '',
            'class_signature': '',
            'struct_class': ''
        }
        lang_lower = language.lower()
        
        # Traverse up to find containing class/module
        current = node.parent
        while current:
            if lang_lower == 'ruby':
                if current.type == 'class':
                    name_node = current.child_by_field_name('name')
                    if name_node:
                        context['wrap_class'] = self.get_node_text(name_node, source_bytes)
                        # Build full class signature from AST
                        signature_parts = ['class', self.get_node_text(name_node, source_bytes)]
                        
                        # Check for superclass
                        superclass_node = current.child_by_field_name('superclass')
                        if superclass_node:
                            signature_parts.append('<')
                            signature_parts.append(self.get_node_text(superclass_node, source_bytes))
                        
                        context['class_signature'] = ' '.join(signature_parts)
                # Ignore modules - only extract actual classes
            
            elif lang_lower == 'php':
                if current.type in ['class_declaration', 'trait_declaration', 'interface_declaration']:
                    name_node = current.child_by_field_name('name')
                    if name_node:
                        context['wrap_class'] = self.get_node_text(name_node, source_bytes)
                        # Build full signature from AST
                        signature_parts = []
                        
                        # Get modifiers (abstract, final, etc.)
                        for child in current.children:
                            if child.type in ['abstract', 'final', 'readonly']:
                                signature_parts.append(self.get_node_text(child, source_bytes))
                        
                        # Add declaration type
                        if current.type == 'class_declaration':
                            signature_parts.append('class')
                        elif current.type == 'trait_declaration':
                            signature_parts.append('trait')
                        elif current.type == 'interface_declaration':
                            signature_parts.append('interface')
                        
                        # Add name
                        signature_parts.append(self.get_node_text(name_node, source_bytes))
                        
                        # Check for extends
                        base_clause = current.child_by_field_name('base_clause')
                        if base_clause:
                            signature_parts.append('extends')
                            signature_parts.append(self.get_node_text(base_clause, source_bytes).replace('extends', '').strip())
                        
                        # Check for implements
                        for child in current.children:
                            if child.type == 'class_interface_clause':
                                signature_parts.append('implements')
                                # Get all interfaces
                                interfaces = []
                                for interface_child in child.children:
                                    if interface_child.type == 'name':
                                        interfaces.append(self.get_node_text(interface_child, source_bytes))
                                signature_parts.append(', '.join(interfaces))
                        
                        context['class_signature'] = ' '.join(signature_parts)
            elif lang_lower == 'rust':
                if current.type == 'impl_item':
                    type_node = current.child_by_field_name('type')
                    trait_node = current.child_by_field_name('trait')
                    if type_node:
                        impl_type = self.get_node_text(type_node, source_bytes).strip()
                        context['wrap_class'] = impl_type
                        if trait_node:
                            trait_name = self.get_node_text(trait_node, source_bytes).strip()
                            context['class_signature'] = f"impl {trait_name} for {impl_type}"
                        else:
                            context['class_signature'] = f"impl {impl_type}"
                        break
            
            current = current.parent
        
        return context
    
    def _get_identifier(self, node: Node, source_bytes: bytes) -> str:
        """Get identifier name from node."""
        for child in node.children:
            if 'identifier' in child.type or 'name' in child.type:
                return self.get_node_text(child, source_bytes)
        return ''
    
    def _find_name_node(self, node: Node) -> Optional[Node]:
        """Find a likely function name node in a subtree."""
        candidate_types = {
            'identifier',
            'field_identifier',
            'type_identifier',
            'constant',
            'name',
        }
        queue = [node]
        while queue:
            current = queue.pop(0)
            if current.type in candidate_types:
                return current
            queue.extend(current.children)
        return None

    def _extract_julia_function_name(self, focal_code: str) -> Optional[str]:
        """Extract Julia callable names from source text.

        tree-sitter-julia does not consistently expose the declared callable as a
        named field. A generic AST walk can therefore pick local identifiers from
        the function body. Keep this source-text extraction scoped to Julia.
        """
        patterns = [
            # function Module.name(args)
            r'function\s+([A-Za-z_][A-Za-z0-9_!]*\.[A-Za-z_][A-Za-z0-9_!]*(?:\{[^\}]*\})?)\s*\(',
            # function name(args)
            r'function\s+([A-Za-z_][A-Za-z0-9_!]*(?:\{[^\}]*\})?)\s*\(',
            # name(args) = body
            r'([A-Za-z_][A-Za-z0-9_!]*(?:\{[^\}]*\})?)\s*\([^\)]*\)\s*=',
            # function (a::Type)(args) ... callable object methods
            r'function\s+\(\s*[A-Za-z_][A-Za-z0-9_!]*\s*::\s*([A-Za-z_][A-Za-z0-9_!\.]*)',
        ]

        for pattern in patterns:
            match = re.search(pattern, focal_code)
            if match:
                return match.group(1)

        return None

    def _strip_assignment_body(self, signature: str) -> str:
        """Strip body from a one-line assignment-style function definition."""
        depth = 0
        for i, char in enumerate(signature):
            if char in "([{":
                depth += 1
            elif char in ")]}" and depth > 0:
                depth -= 1
            elif char == '=' and depth == 0:
                return signature[:i].strip()
        return signature.strip()

    def _extract_multiline_signature(self, focal_code: str, first_line: str) -> str:
        """Extract complete signature by tracking parenthesis depth across lines."""
        if not first_line:
            return ""

        # Check if signature ends on first line (has closing paren before newline)
        if ')' in first_line:
            return first_line.strip()

        # Multi-line: collect lines until parenthesis closes
        signature_lines = [first_line]
        depth = first_line.count('(') - first_line.count(')')

        for line in focal_code.split('\n')[1:]:
            stripped = line.strip()
            if not stripped:
                continue
            signature_lines.append(stripped)
            depth += stripped.count('(') - stripped.count(')')
            if depth <= 0:
                break

        return ' '.join(signature_lines).strip()

    def _extract_signature(self, focal_code: str, language: str) -> str:
        """Extract complete function signature from focal_code for all languages."""
        first_non_empty = next((line.strip() for line in focal_code.splitlines() if line.strip()), "")
        if not first_non_empty:
            return ""

        # For assignment-style (fn foo() = body or name(args) = body)
        if '=' in first_non_empty:
            return self._strip_assignment_body(first_non_empty)

        # Check if signature ends on first line (has closing paren)
        if ')' in first_non_empty:
            signature = first_non_empty.strip()
            # Strip trailing '{' only for brace-delimited languages (Go, Rust)
            if language.lower() in ('go', 'rust'):
                return signature.rstrip('{').strip()
            return signature.strip()

        # Multi-line: track parenthesis depth until closes
        return self._extract_multiline_signature(focal_code, first_non_empty)

    def extract_package_name(self, file_content: str, language: str) -> str:
        """Extract package/module/namespace name."""
        lines = file_content.split('\n')
        lang_lower = language.lower()
        
        if lang_lower == 'go':
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('package '):
                    match = re.match(r'package\s+([A-Za-z_]\w*)', stripped)
                    if match:
                        return match.group(1)
        
        elif lang_lower == 'julia':
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('module ') or stripped.startswith('baremodule '):
                    match = re.match(r'(?:baremodule|module)\s+([A-Za-z_]\w*)', stripped)
                    if match:
                        return match.group(1)
        
        elif lang_lower == 'ruby':
            for line in lines:
                if line.strip().startswith('module '):
                    match = re.match(r'module\s+(\w+)', line)
                    if match:
                        return match.group(1)
        
        elif lang_lower == 'php':
            for line in lines:
                if line.strip().startswith('namespace '):
                    match = re.match(r'namespace\s+([\w\\]+)', line)
                    if match:
                        return match.group(1)
        
        return ''
    
    def get_function_nodes(self, root: Node, language: str) -> List[Node]:
        """Get all function/method nodes from AST."""
        function_nodes = []
        
        lang_lower = language.lower()
        
        # Define function node types per language
        function_types = {
            'go': ['function_declaration', 'method_declaration'],
            'rust': ['function_item'],
            'julia': ['function_definition', 'short_function_definition'],
            'ruby': ['method', 'singleton_method'],
            'php': ['method_declaration', 'function_definition']
        }
        
        target_types = function_types.get(lang_lower, [])
        
        def traverse(node: Node):
            if node.type in target_types:
                function_nodes.append(node)
            
            for child in node.children:
                traverse(child)
        
        traverse(root)
        return function_nodes
    
    def parse_source_file(self, file_path: str, language: str, repo_name: str, 
                         repo_path: str = None) -> List[FunctionMetadata]:
        """Parse source file and extract all qualifying functions."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                file_content = f.read()
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return []
        
        # Parse with tree-sitter
        root = self.parser.parse(file_content, language)
        if not root:
            return []
        
        source_bytes = bytes(file_content, 'utf8')
        package_name = self.extract_package_name(file_content, language)
        
        # Get all function nodes
        function_nodes = self.get_function_nodes(root, language)
        
        functions = []
        for func_node in function_nodes:
            try:
                func_metadata = self._extract_function_metadata(
                    func_node, source_bytes, file_path, file_content,
                    language, repo_name, package_name
                )
                
                if func_metadata and self.filter_function(func_metadata):
                    functions.append(func_metadata)
            except Exception as e:
                print(f"Error extracting function from {file_path}: {e}")
        
        return functions
    
    def _extract_function_metadata(self, node: Node, source_bytes: bytes, 
                                   file_path: str, file_content: str,
                                   language: str, repo_name: str, 
                                   package_name: str) -> Optional[FunctionMetadata]:
        """Extract complete metadata for a function."""
        focal_code = self.get_node_text(node, source_bytes)
        lang_lower = language.lower()

        if lang_lower == 'julia':
            function_name = self._extract_julia_function_name(focal_code)
        else:
            # Get function name
            name_node = node.child_by_field_name('name')
            if not name_node:
                signature_node = node.child_by_field_name('signature')
                if signature_node:
                    name_node = signature_node.child_by_field_name('name')
                    if not name_node:
                        name_node = self._find_name_node(signature_node)
            
            if not name_node:
                name_node = self._find_name_node(node)
            
            if not name_node:
                return None
            
            function_name = self.get_node_text(name_node, source_bytes)

        if not function_name:
            return None
        
        # Create relative file path with repo_name
        # Convert absolute path to relative path including repo_name
        relative_file_path = file_path
        try:
            path_obj = Path(file_path)
            # Find the repo_name in the path and create relative path from there
            parts = path_obj.parts
            if repo_name in parts:
                repo_index = parts.index(repo_name)
                relative_file_path = str(Path(*parts[repo_index:])).replace('\\', '/')
            else:
                # Fallback: use repo_name + filename
                relative_file_path = f"{repo_name}/{path_obj.name}"
        except Exception:
            relative_file_path = f"{repo_name}/{Path(file_path).name}"
        file_path = relative_file_path
        
        # Get class context
        class_context = self.get_class_context(node, source_bytes, language)
        
        # Build signature
        signature = self._extract_signature(focal_code, language)
        
        # Create function component
        function_component = FunctionComponent(
            name=function_name,
            signature=signature,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1
        )
        
        # Build metadata dict with language-specific fields (always include all fields)
        metadata = {}
        # Package/Module/Namespace (language-specific naming)
        if lang_lower == 'go':
            metadata['package'] = package_name if package_name else ''
        elif lang_lower == 'julia':
            metadata['module'] = package_name if package_name else ''
        elif lang_lower == 'ruby':
            metadata['module'] = package_name if package_name else ''
        elif lang_lower == 'php':
            metadata['namespace'] = package_name if package_name else ''
        
        # Class information
        metadata['class_name'] = class_context['wrap_class'] if class_context['wrap_class'] else ''
        metadata['class_signature'] = class_context['class_signature'] if class_context['class_signature'] else ''
        
        return FunctionMetadata(
            function_name=function_name,
            file_path=file_path,
            focal_code=focal_code,
            file_content=file_content,
            language=language,
            function_component=asdict(function_component),
            metadata=metadata
        )
    
    def filter_function(self, func_metadata: FunctionMetadata) -> bool:
        """Filter function based on language-specific rules."""
        focal_code = func_metadata.focal_code
        function_name = func_metadata.function_name
        language = func_metadata.language
        file_path = func_metadata.file_path
        lang_lower = language.lower()
        
        # Normalize path separators for consistent checking
        file_path_normalized = file_path.replace('\\', '/')
        file_path_lower = file_path_normalized.lower()
        
        # FIRST: Exclude vendor/dependency folders (highest priority)
        excluded_folders = [
            '/vendor/', '/node_modules/', '/gems/', '/bower_components/',
            '/.bundle/', '/packages/', '/third_party/', '/external/',
            '/.phpstan/', '/build/', '/dist/', '/target/', '/out/'
        ]
        for folder in excluded_folders:
            if folder in file_path_lower:
                return False
        
        # Also check if path starts with these folders
        excluded_starts = [
            'vendor/', 'node_modules/', 'gems/', 'bower_components/',
            '.bundle/', 'packages/', 'third_party/', 'external/',
            '.phpstan/', 'build/', 'dist/', 'target/', 'out/'
        ]
        for folder in excluded_starts:
            if file_path_lower.startswith(folder):
                return False
        
        path_parts = file_path_normalized.split('/')
        
        # Get language-specific rules with optional per-repository overrides.
        lang_rules = self.filter_rules.get(lang_lower, {})
        repo_name = (path_parts[0] if path_parts else '').lower()
        repo_rules = self.repo_filter_rules.get(lang_lower, {}).get(repo_name, {})
        if repo_rules:
            lang_rules = {**lang_rules, **repo_rules}
        
        # Only include functions from specific source folders (if configured).
        # Match source roots anywhere under the repository path so nested workspaces
        # (e.g. rust multi-crate repos with crate/src/...) are handled correctly.
        source_roots = [root.lower() for root in lang_rules.get('source_roots', []) if root]
        
        if source_roots:
            path_dirs = [part.lower() for part in path_parts[1:-1] if part]
            if not any(part in source_roots for part in path_dirs):
                return False
        
        # Exclude language-specific path patterns (if configured)
        exclude_path_contains = [pattern.lower() for pattern in lang_rules.get('exclude_path_contains', [])]
        for pattern in exclude_path_contains:
            if pattern and pattern in file_path_lower:
                return False
        
        # Exclude functions from test/spec folders
        if lang_lower == 'ruby':
            # Exclude test/ and spec/ folders for Ruby
            if '/test/' in file_path_lower or '/spec/' in file_path_lower:
                return False
            if file_path_lower.startswith('test/') or file_path_lower.startswith('spec/'):
                return False
        elif lang_lower == 'php':
            # Exclude test/ folder for PHP
            if '/test/' in file_path_lower or file_path_lower.startswith('test/'):
                return False
            
            # Exclude protected, private, and abstract methods in PHP
            focal_code_lower = focal_code.lower()
            if 'protected function' in focal_code_lower or 'protected static function' in focal_code_lower:
                return False
            if 'private function' in focal_code_lower or 'private static function' in focal_code_lower:
                return False
            if 'abstract function' in focal_code_lower or 'abstract protected function' in focal_code_lower:
                return False
            if 'abstract public function' in focal_code_lower or 'abstract static function' in focal_code_lower:
                return False
        
        min_lines = lang_rules.get('min_lines', 20)
        max_lines = lang_rules.get('max_lines', 50)
        exclude_patterns = lang_rules.get('exclude_patterns', [])
        exclude_prefixes = lang_rules.get('exclude_prefixes', ['_', '$'])
        
        # Exclude main, run, and common utility functions
        if function_name in self.exclude_functions:
            return False
        
        # Exclude functions matching language-specific patterns
        for pattern in exclude_patterns:
            if pattern.lower() in function_name.lower():
                return False
        
        # Exclude private/internal functions (language-specific prefixes)
        for prefix in exclude_prefixes:
            if function_name.startswith(prefix):
                return False
        
        # Exclude getters/setters (common patterns)
        if function_name.startswith('get') and len(function_name) > 3 and function_name[3].isupper():
            return False
        if function_name.startswith('set') and len(function_name) > 3 and function_name[3].isupper():
            return False
        
        # Check line count (language-specific limits)
        line_count = self.count_lines(focal_code)
        if line_count < min_lines or line_count > max_lines:
            return False
        
        # Parse again to check return statement
        root = self.parser.parse(focal_code, func_metadata.language)
        if not root:
            return False
        
        # Check for return statement
        if not self.has_return_statement(root, func_metadata.language):
            return False
        
        return True
