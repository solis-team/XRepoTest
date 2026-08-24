import re
from typing import List, Dict, Optional, Tuple
from xrepotest.lsp.argument_extractors.base_extractor import BaseArgumentExtractor


class JuliaArgumentExtractor(BaseArgumentExtractor):
    """Julia-specific argument extractor."""

    def get_language(self) -> str:
        """Return Julia language identifier."""
        return "julia"
        
    def extract_function_arguments(self, function_signature: str) -> List[Dict]:
        """Extract argument names and types from a Julia function signature"""
        signature = self._normalize_whitespace(function_signature)

        # Remove function keyword and return type
        signature = re.sub(r'^function\s+', '', signature)
        signature = re.sub(r'\)\s*::[^)]*$', ')', signature)
        
        # Extract function name and parameters
        # Handle callable object methods like: (a::Layer)(x::Array)
        callable_match = re.match(r'\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*::\s*([^)]+)\)\s*\((.*)\)', signature.strip())
        if callable_match:
            params_str = f"{callable_match.group(1)}::{callable_match.group(2)}, {callable_match.group(3)}"
        else:
            params_str = self._extract_parameter_list(signature.strip())

        if params_str is None:
            return []
        
        arguments = []
        if params_str.strip():
            params = self._split_parameters(params_str)
            
            for param in params:
                arg_info = self._parse_parameter(param.strip())
                if arg_info:
                    arguments.append(arg_info)
        return arguments
    
    def _parse_parameter(self, param: str) -> Optional[Dict]:
        """Parse a single parameter to extract name and type"""
        param = param.strip().lstrip(';').strip()
        if not param:
            return None

        if '::' in param:
            name_part, type_part = param.split('::', 1)
            name = self._strip_default_value(name_part).strip()
            type_name = self._strip_default_value(type_part).strip()
            
            # Handle parametric types
            if '{' in type_name:
                type_name = type_name.split('{')[0]
            
            # Handle where clauses
            if ' where ' in type_name:
                type_name = type_name.split(' where ')[0]
            
            return {
                'name': name,
                'type': type_name,
                'type_components': self._extract_type_components(type_name),
                'full_signature': param
            }
        else:
            # Handle untyped parameters
            name = self._strip_default_value(param).strip()
            if name.endswith('...'):
                return {
                    'name': name[:-3],
                    'type': 'Vararg',
                    'type_components': self._extract_type_components('Vararg'),
                    'full_signature': param
                }
            else:
                return {
                    'name': name,
                    'type': 'Any',
                    'type_components': self._extract_type_components('Any'),
                    'full_signature': param
                }

    def _extract_parameter_list(self, signature: str) -> Optional[str]:
        """Return the outer function parameter list from a Julia signature."""
        for i, char in enumerate(signature):
            # Operator function names can look like Base.:(==)(x, y). The first
            # parenthesized group is part of the name, not the argument list.
            if char != '(' or (i > 0 and signature[i - 1] == ':'):
                continue

            depth = 0
            for j in range(i, len(signature)):
                if signature[j] == '(':
                    depth += 1
                elif signature[j] == ')':
                    depth -= 1
                    if depth == 0:
                        return signature[i + 1:j]

        return None

    def _split_parameters(self, params_str: str, delimiters: Optional[str] = None) -> List[str]:
        """Split Julia parameters by top-level commas or keyword semicolons."""
        params = []
        current = []
        depth = 0
        opening = set("([{")
        closing = set(")]}")

        for char in params_str:
            if char in ",;" and depth == 0:
                if current:
                    params.append(''.join(current).strip())
                current = []
                continue

            if char in opening:
                depth += 1
            elif char in closing and depth > 0:
                depth -= 1
            current.append(char)

        if current:
            params.append(''.join(current).strip())

        return params

    def _strip_default_value(self, value: str) -> str:
        """Strip a top-level default assignment from a Julia parameter fragment."""
        depth = 0
        opening = set("([{")
        closing = set(")]}")

        for i, char in enumerate(value):
            if char in opening:
                depth += 1
            elif char in closing and depth > 0:
                depth -= 1
            elif char == '=' and depth == 0:
                if i > 0 and value[i - 1] in ('<', '>', '=', '!'):
                    continue
                return value[:i].strip()

        return value.strip()

    def _extract_type_components(self, type_name: str) -> List[str]:
        """Extract Julia type components, including parametric type roots."""
        if not type_name:
            return []

        root = type_name.split("{", 1)[0].strip()
        if not root:
            return []
        return [root]
    
    def get_argument_definitions(self, file_path: str, function_signature: str) -> Dict[str, Dict]:
        """Get definitions for all arguments in a function signature"""
        arguments = self.extract_function_arguments(function_signature)
        definitions = {}

        if not self.lsp_client:
            return definitions
        
        # Use centralized type filtering from TokenClassifier
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.lsp_client.open_document(file_path, content)
        
        for arg in arguments:
            arg_type = arg['type']
            
            # Skip known types
            if arg_type in self.builtin_types:
                continue
            
            # Find the position of the type in the file
            type_positions = self._find_type_positions(content, arg_type)
            
            arg_definitions = {}
            for line, char in type_positions:
                try:
                    definition_locs = self.lsp_client.goto_definition(file_path, line, char)
                    if definition_locs:
                        def_loc = definition_locs[0]
                        def_content = self._get_definition_content_extended(def_loc)
                        
                        arg_definitions[arg_type] = {
                            'type_definition': def_content,
                            'definition_location': def_loc
                        }
                        break
                except Exception as e:
                    print(f"Error getting definition for {arg_type}: {e}")
            
            if arg_definitions:
                definitions[arg['name']] = {
                    'type': arg_type,
                    'definitions': arg_definitions
                }
        
        return definitions
    
    def _find_type_positions(self, content: str, type_name: str) -> List[Tuple[int, int]]:
        positions = []
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines):
            start = 0
            while True:
                pos = line.find(type_name, start)
                if pos == -1:
                    break
                
                if (pos == 0 or not line[pos-1].isalnum()) and \
                   (pos + len(type_name) >= len(line) or not line[pos + len(type_name)].isalnum()):
                    positions.append((line_num, pos))
                
                start = pos + 1
        
        return positions
    
    def _get_definition_content(self, definition_location: Dict) -> str:
        uri = definition_location['uri']
        range_info = definition_location['range']
        
        file_path = uri.replace('file://', '')
        
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()
            
            start_line = range_info['start']['line']
            end_line = range_info['end']['line']
            
            if start_line == end_line:
                content = lines[start_line][range_info['start']['character']:range_info['end']['character']]
            else:
                content_lines = []
                content_lines.append(lines[start_line][range_info['start']['character']:])
                for i in range(start_line + 1, end_line):
                    content_lines.append(lines[i])
                content_lines.append(lines[end_line][:range_info['end']['character']])
                content = ''.join(content_lines)
            return content.strip()
        except Exception as e:
            print(f"Error reading definition content: {e}")
            return ""
    
    def _get_definition_content_extended(self, definition_location: Dict) -> str:
        """Get extended definition content for Julia types (including full struct/type blocks)"""
        uri = definition_location['uri']
        range_info = definition_location['range']
        
        file_path = uri.replace('file://', '')
        
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()
            
            start_line = range_info['start']['line']
            
            # Read the full type definition block (until 'end')
            block_lines = []
            indent_level = None
            
            for i in range(start_line, len(lines)):
                line = lines[i]
                
                if i == start_line:
                    block_lines.append(line.rstrip())
                    # Determine base indentation
                    indent_level = len(line) - len(line.lstrip())
                    continue
                
                stripped = line.strip()
                
                # Skip empty lines and comments
                if not stripped or stripped.startswith('#'):
                    block_lines.append(line.rstrip())
                    continue
                
                # Check for end keyword at same or lower indentation
                current_indent = len(line) - len(line.lstrip())
                if current_indent <= indent_level and stripped == 'end':
                    block_lines.append(line.rstrip())
                    break
                
                block_lines.append(line.rstrip())
                
                # Limit to reasonable size
                if len(block_lines) > 100:
                    break
            
            return '\n'.join(block_lines)
        except Exception as e:
            print(f"Error reading extended definition content: {e}")
            return ""


def main():
    pass


if __name__ == "__main__":
    main()
