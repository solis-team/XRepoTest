import re
from typing import List, Dict, Optional
from pathlib import Path
from xrepotest.lsp.argument_extractors.base_extractor import BaseArgumentExtractor


class GoArgumentExtractor(BaseArgumentExtractor):
    """Go-specific argument extractor."""
    
    def get_language(self) -> str:
        """Return Go language identifier."""
        return 'go'
    
    def get_delimiters(self) -> str:
        """Go uses braces, brackets, and parentheses for nesting."""
        return '{[()]}' 
    
    def extract_function_arguments(self, function_signature: str) -> List[Dict]:
        """Extract argument names and types from Go function signature"""
        # Normalize whitespace and remove comments
        signature = self._normalize_whitespace(function_signature)
        signature = re.sub(r'//.*?$', '', signature, flags=re.MULTILINE)
        
        # Remove receiver if present
        signature = re.sub(r'^func\s*\([^)]*\)\s*', 'func ', signature)
        
        # Remove return type
        signature = re.sub(r'\)\s*\(?[^{]+$', ')', signature)
        
        # Extract parameters
        # Handle package-qualified names: chi.NewRouter, receiver methods, or simple functions
        match = re.search(r'func\s+(?:[\w\.]+)?\s*\((.*?)\)', signature)
        if not match:
            return []
        
        params_str = match.group(1).strip()
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
        """Parse a Go parameter and extract type components"""
        # Handle named parameters (name type) and anonymous parameters (type)
        parts = param.rsplit(' ', 1)
        if len(parts) == 1:
            # Anonymous parameter
            name = parts[0]
            type_name = ''
        else:
            # Named parameter
            name, type_name = parts
        
        # Handle variadic parameters
        is_variadic = type_name.startswith('...')
        if is_variadic:
            type_name = type_name[3:]
        
        # Handle pointer types
        is_pointer = type_name.startswith('*')
        if is_pointer:
            type_name = type_name[1:]
        
        # Handle channel types
        is_channel = type_name.startswith('chan ')
        if is_channel:
            type_name = type_name[5:]
        
        return {
            'name': name.strip(),
            'type': type_name.strip(),
            'type_components': self._extract_type_components(type_name),
            'full_signature': param
        }
    
    def _extract_type_components(self, type_name: str) -> List[str]:
        """Extract all type names including nested types"""
        # Remove array brackets
        clean_type = re.sub(r'\[[^\]]*\]', '', type_name)
        
        # Handle struct types
        if clean_type.startswith('struct{') and clean_type.endswith('}'):
            return self._process_struct_fields(clean_type[7:-1])
        
        # Handle interface types
        if clean_type.startswith('interface{') and clean_type.endswith('}'):
            return ['interface{}']
        
        # Handle function types
        if clean_type.startswith('func('):
            return ['func']
        
        # Split package prefixes
        main_type = clean_type.split('.')[-1]
        components = [main_type]
        
        # Handle map types
        if 'map[' in clean_type:
            map_match = re.match(r'map\[([^\]]+)\](.+)', clean_type)
            if map_match:
                key_type = map_match.group(1)
                value_type = map_match.group(2)
                components.extend(self._extract_type_components(key_type))
                components.extend(self._extract_type_components(value_type))
        
        # Handle generic types (Go 1.18+)
        if '[' in clean_type and ']' in clean_type:
            inner_types = re.search(r'\[(.*)\]', clean_type)
            if inner_types:
                for nested in self._split_generic_params(inner_types.group(1)):
                    components.extend(self._extract_type_components(nested))
        
        return [c for c in components if c and not c.isspace()]
    
    def _split_generic_params(self, params: str) -> List[str]:
        """Split generic parameters while handling nested types"""
        parts = []
        current = []
        depth = 0
        
        for char in params:
            if char == ',' and depth == 0:
                parts.append(''.join(current).strip())
                current = []
            else:
                if char in '{[(':
                    depth += 1
                elif char in '}])':
                    depth -= 1
                current.append(char)
        
        if current:
            parts.append(''.join(current).strip())
        return parts
    
    def _process_struct_fields(self, struct_fields: str) -> List[str]:
        """Handle Go struct field types"""
        components = []
        for field in self._split_parameters(struct_fields):
            if ' ' in field:
                # Named field: "Name Type" or "Name Type `tag`"
                field_type = field.split(' ', 1)[1].split('`')[0].strip()
                components.extend(self._extract_type_components(field_type))
        return components
    
    def get_argument_definitions(self, file_path: str, function_signature: str) -> Dict[str, Dict]:
        """Get definitions for all argument types in a function signature"""
        arguments = self.extract_function_arguments(function_signature)
        definitions =[]
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if self.lsp_client:
            self.lsp_client.open_document(file_path, content)
        
        for arg in arguments:
            arg_definitions =[]
            for type_component in arg.get('type_components', []):
                try:
                    line, char = self._find_type_position(content, type_component,arg.get('full_signature', ""))
                    if line is None or char is None:
                        continue
                    if line is not None and char is not None:
                        type_def = self._get_type_definition(file_path, line, char, content)

                        if type_def and "func" not in type_def["type_definition"]:
                            arg_definitions.append(type_def)
                except Exception as e:
                    print(f"Error getting definition for {type_component}: {e}")
            
            if arg_definitions :
                definitions.append( {
                    'name': arg['name'],
                    'type': arg['type'],
                    'definitions': arg_definitions,
                })
        
        return definitions

    def _find_type_position(self, content: str, type_name: str, argument: str) :
        """Find the position of type_name in function signatures.
        If not found, fallback to position of argument name in signatures.
        Only returns the first match (line, column).
        """
        import re
        
        # Use centralized type filtering from TokenClassifier
        if not type_name or type_name in self.builtin_types:
            return None, None

        lines = content.splitlines()
        func_signature_pattern = re.compile(r'^\s*func\s+')
        type_pattern = re.compile(rf'\b{re.escape(type_name)}\b')
        arg_pattern = re.compile(rf'\b{re.escape(argument)}\b')

        for i, line in enumerate(lines):
            if func_signature_pattern.match(line):
                match = type_pattern.search(line)
                if match:
                    return i, match.start()
        if( not argument):
            return None, None
        # If not found, fallback to argument
        for i, line in enumerate(lines):
            if func_signature_pattern.match(line):
                match = arg_pattern.search(line)
                if match:
                    return i, match.start()
        
        return None, None

        
    def _get_type_definition(self, file_path: str, line: int, char: int, content: str) -> Dict:
        """Get complete type definition including implementations"""
        if not self.lsp_client:
            return None
        type_defs = self.lsp_client.goto_definition(file_path, line, char)
        if not type_defs:
            type_defs = self.lsp_client.goto_type_definition(file_path, line, char)
        if not type_defs:
            return None

        type_def = type_defs[0]
        def_path = Path(type_def["uri"].replace("file://", ""))
        
        # If path doesn't exist, try resolving relative to project_path
        if not def_path.exists() and self.lsp_client.project_path:
            # Handle workspace-relative paths like /Go-master/...
            relative_path = str(def_path).lstrip('/')
            if '/' in relative_path:
                # Extract path after first directory component
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
        """Extract a complete Go type or function block starting from the definition line."""
        block_lines = []
        brace_count = 0
        started = False

        def strip_comments_and_strings(line: str) -> str:
            """Remove comments and strings that might contain brace-like characters."""
            line = re.sub(r'//.*', '', line)  # Remove line comments
            line = re.sub(r'/\*.*?\*/', '', line, flags=re.DOTALL)  # Remove block comments
            line = re.sub(r'`[^`]*`', '', line)  # Remove raw strings
            line = re.sub(r'"(?:\\.|[^"\\])*"', '', line)  # Remove string literals
            return line

        # Get and clean the initial line
        line0 = lines[start_line]
        line0_clean = strip_comments_and_strings(line0).strip()

        # --- Case 1: Single-line definitions ---
        # type Foo struct{...} or type Bar interface{...}
        if re.match(r'^type\s+\w+\s+(struct|interface)\s*\{.*\}', line0_clean):
            return line0
        
        # type Foo = Bar or type Foo int
        if re.match(r'^type\s+\w+\s+[\w*\[\],]+(?:\s|$)', line0_clean) and "{" not in line0_clean:
            return line0

        # --- Case 2: Multi-line definitions ---
        # Collect all lines that are part of the declaration before the opening brace
        declaration_lines = [line0]
        
        # Check if the opening brace is already on the first line
        if '{' in line0_clean:
            # Brace is on line0, no need to search further
            # start_line is already correct, skip to Case 3
            pass
        else:
            # Search for the opening brace in subsequent lines
            for i in range(start_line + 1, len(lines)):
                current_line = lines[i]
                current_clean = strip_comments_and_strings(current_line)
                
                # Check if this line has the opening brace
                if '{' in current_clean:
                    declaration_lines.append(current_line)
                    start_line = i  # Update the starting line for brace counting
                    break
                
                # If we hit something that's clearly not part of the declaration, stop
                if current_clean.strip() and not re.match(r'^[\s]*(\w+|\))', current_clean):
                    break
                    
                declaration_lines.append(current_line)

        # --- Case 3: Read block using brace counting ---
        for i in range(start_line, len(lines)):
            line = lines[i]
            clean = strip_comments_and_strings(line)

            open_braces = clean.count('{')
            close_braces = clean.count('}')
            brace_count += open_braces - close_braces

            if open_braces > 0:
                started = True
            
            # Include the line in the result if it's part of the declaration
            if i == start_line or started:
                block_lines.append(line)

            if started and brace_count == 0:
                break

        # Combine the declaration lines with the block lines
        if not started:
            # No braces found, return just the declaration
            return "\n".join(declaration_lines)
        else:
            # The last line in declaration_lines is the line with '{' which is also
            # the first line in block_lines (start_line). Remove it from declaration_lines
            # to avoid duplication.
            if declaration_lines and block_lines:
                result_lines = declaration_lines[:-1] + block_lines
            else:
                result_lines = declaration_lines + block_lines
        # Remove trailing empty lines
            return "\n".join(result_lines).rstrip()



