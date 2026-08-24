import logging
import re
from typing import List, Dict, Optional
from pathlib import Path
from xrepotest.lsp.argument_extractors.base_extractor import BaseArgumentExtractor

logger = logging.getLogger(__name__)


class RubyArgumentExtractor(BaseArgumentExtractor):
    """Ruby-specific argument extractor."""

    def get_language(self) -> str:
        """Return Ruby language identifier."""
        return "ruby"
        
    def extract_function_arguments(self, function_signature: str) -> List[Dict]:
        """Extract argument names from Ruby method signature
        Note: Ruby is dynamically typed, so type information comes from YARD docs or Sorbet/RBS"""
        # Normalize whitespace and remove comments
        signature = self._normalize_whitespace(function_signature)
        signature = re.sub(r'#.*?$', '', signature, flags=re.MULTILINE)
        
        # Extract parameters from def method_name(params)
        # Handle class-qualified names: MyClass.method, MyClass#method, or simple method names
        match = re.search(r'def\s+([\w:.#]+)\s*\((.*?)\)', signature)
        if not match:
            # Method with no parentheses: def method_name
            return []
        
        params_str = match.group(2).strip()
        if not params_str:
            return []
        
        arguments = []
        for param in self._split_parameters(params_str):
            param = param.strip()
            if not param:
                continue
                
            arg_info = self._parse_parameter(param)
            if arg_info:
                arguments.append(arg_info)
        
        return arguments
    
    def _parse_parameter(self, param: str) -> Optional[Dict]:
        """Parse a Ruby parameter
        Formats: name, name:, name = default, name:, *args, **kwargs, &block"""
        # Skip block parameters
        if param.startswith('&'):
            return None
        
        # Handle splat operators
        is_splat = param.startswith('*') and not param.startswith('**')
        is_double_splat = param.startswith('**')
        
        if is_splat:
            param = param[1:]
        elif is_double_splat:
            param = param[2:]
        
        # Remove default values
        if '=' in param:
            param = param.split('=')[0].strip()
        
        # Remove keyword argument colon
        if param.endswith(':'):
            param = param[:-1]
        
        name = param.strip()
        
        return {
            'name': name,
            'type': 'Unknown',  # Ruby is dynamically typed
            'type_components': self._extract_type_components('Unknown'),
            'is_splat': is_splat,
            'is_double_splat': is_double_splat,
            'full_signature': param
        }

    def _extract_type_components(self, type_name: str) -> List[str]:
        """Ruby is dynamic; typed components come from docs or external typing tools."""
        return [] if not type_name or type_name == "Unknown" else [type_name]
    
    def get_argument_definitions(self, file_path: str, function_signature: str) -> Dict[str, Dict]:
        """Get definitions for Ruby method arguments
        Note: Ruby is dynamically typed, so this primarily looks for class definitions
        referenced in YARD documentation or inferred by Solargraph"""
        arguments = self.extract_function_arguments(function_signature)
        definitions = {}
        
        # Ruby types to skip (common stdlib classes that LLMs already know)
        RUBY_SKIP_TYPES = {
            # Core classes
            'Object', 'Class', 'Module',
            'String', 'Symbol', 'Integer', 'Float', 'Numeric',
            'Array', 'Hash', 'Set',
            'Range', 'Regexp',
            'TrueClass', 'FalseClass', 'NilClass',
            'Proc', 'Lambda', 'Method',
            
            # IO and Files
            'IO', 'File', 'Dir', 'Pathname',
            'StringIO', 'STDIN', 'STDOUT', 'STDERR',
            
            # Time
            'Time', 'Date', 'DateTime',
            
            # Exceptions
            'Exception', 'StandardError', 'RuntimeError', 'ArgumentError',
            'TypeError', 'NameError', 'NoMethodError',
            
            # Enumerable
            'Enumerable', 'Enumerator',
            
            # Thread/Sync
            'Thread', 'Mutex', 'Queue',
            
            # Struct
            'Struct', 'OpenStruct',
            
            # Other common
            'Binding', 'Fiber', 'ObjectSpace',
            'Random', 'Rational', 'Complex',
        }
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if self.lsp_client:
            self.lsp_client.open_document(file_path, content)
        
        # For Ruby, we'll try to extract type information from YARD comments
        type_hints = self._extract_yard_types(content, function_signature)
        
        for arg in arguments:
            arg_name = arg['name']
            # Check if YARD comment provides type hint
            if arg_name in type_hints:
                yard_type = type_hints[arg_name]
                
                # Skip known types
                if yard_type in RUBY_SKIP_TYPES:
                    continue
                
                arg_definitions = {}
                
                try:
                    # Try to find and get definition for the YARD type
                    line, char = self._find_type_in_yard(content, yard_type)
                    if line is not None and char is not None:
                        type_def = self._get_type_definition(file_path, line, char, content)
                        if type_def:
                            arg_definitions[yard_type] = type_def
                except Exception as e:
                    logger.debug(f"YARD type lookup failed for '{yard_type}': {e}")
                
                if arg_definitions:
                    definitions[arg_name] = {
                        'type': yard_type,
                        'definitions': arg_definitions,
                        'is_dynamic': True
                    }
        
        return definitions
    
    def _extract_yard_types(self, content: str, function_signature: str) -> Dict[str, str]:
        """Extract type information from YARD documentation comments"""
        type_hints = {}
        lines = content.splitlines()
        
        # Find the method definition line
        for i, line in enumerate(lines):
            if function_signature.split('(')[0].strip() in line:
                # Look backwards for YARD comments
                for j in range(i - 1, max(0, i - 20), -1):
                    yard_line = lines[j].strip()
                    if not yard_line.startswith('#'):
                        break
                    # Match @param [Type] name
                    match = re.match(r'#\s*@param\s+\[([^\]]+)\]\s+(\w+)', yard_line)
                    if match:
                        type_name = match.group(1).split(',')[0].strip()  # Handle multiple types
                        param_name = match.group(2)
                        type_hints[param_name] = type_name
                break
        
        return type_hints
    
    def _find_type_in_yard(self, content: str, type_name: str) -> tuple:
        """Find position of a class/module definition"""
        lines = content.splitlines()
        
        # Look for class/module definitions
        class_pattern = re.compile(rf'^\s*class\s+{re.escape(type_name)}\b')
        module_pattern = re.compile(rf'^\s*module\s+{re.escape(type_name)}\b')
        
        for i, line in enumerate(lines):
            if class_pattern.match(line) or module_pattern.match(line):
                char_index = line.index(type_name)
                return i, char_index
        
        raise ValueError(f"Cannot find definition of `{type_name}`")
    
    def _get_type_definition(self, file_path: str, line: int, char: int, content: str) -> Dict:
        """Get complete type definition"""
        if not self.lsp_client:
            return None

        type_defs = self.lsp_client.goto_definition(file_path, line, char)
        if not type_defs:
            return None

        type_def = type_defs[0]
        def_path = Path(type_def["uri"].replace("file://", ""))
        
        # If path doesn't exist, try resolving relative to project_path
        if not def_path.exists() and hasattr(self.lsp_client, 'project_path') and self.lsp_client.project_path:
            relative_path = str(def_path).lstrip('/')
            if '/' in relative_path:
                parts = relative_path.split('/', 1)
                if len(parts) > 1:
                    def_path = self.lsp_client.project_path / parts[1]
        
        start_line = type_def["range"]["start"]["line"]

        try:
            with open(def_path, 'r', encoding='utf-8') as f:
                def_lines = f.read().splitlines()
            type_block = self._get_definition_content(def_lines, start_line)
        except Exception as e:
            print(f"Error reading definition file {def_path}: {e}")
            type_block = ""

        return {
            'type_definition': type_block,
            'definition_location': type_def
        }

    def _get_definition_content(self, lines: List[str], start_line: int) -> str:
        """Extract a complete Ruby class/module block"""
        block_lines = []
        indent_level = None
        started = False

        for i in range(start_line, len(lines)):
            line = lines[i]
            
            if i == start_line:
                block_lines.append(line)
                # Determine base indentation
                indent_level = len(line) - len(line.lstrip())
                started = True
                continue
            
            if not started:
                continue
            
            stripped = line.strip()
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                block_lines.append(line)
                continue
            
            # Check for end keyword at same or lower indentation
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= indent_level and stripped == 'end':
                block_lines.append(line)
                break
            
            block_lines.append(line)

        return "\n".join(block_lines)
