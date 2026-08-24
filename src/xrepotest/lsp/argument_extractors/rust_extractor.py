import logging
import re
import time
from typing import List, Dict, Optional
from pathlib import Path
from xrepotest.lsp.argument_extractors.base_extractor import BaseArgumentExtractor

logger = logging.getLogger(__name__)


class RustArgumentExtractor(BaseArgumentExtractor):
    """Rust-specific argument extractor."""
    
    def get_language(self) -> str:
        """Return Rust language identifier."""
        return 'rust'
    
    def get_delimiters(self) -> str:
        """Rust uses angle brackets, parens, braces, and brackets."""
        return '<>(){}[]'
        
    def extract_function_arguments(self, function_signature: str) -> List[Dict]:
        """Extract argument names and types with nested type components"""
        # Normalize whitespace and remove comments/attributes
        signature = self._normalize_whitespace(function_signature)
        signature = re.sub(r'#\[[^\]]*\]', '', signature)
        signature = re.sub(r'///.*$', '', signature, flags=re.MULTILINE)
        
        # Remove visibility modifiers and return type
        signature = re.sub(r'^\s*pub\s+(?=fn)', '', signature)
        signature = re.sub(r'->\s*[^{;]+', '', signature)
        
        # Extract parameters
        # Handle module-qualified names: std::io::read or simple function names
        match = re.search(r'fn\s+(?:[\w:]+)\s*\((.*?)\)', signature)
        if not match:
            return []
        
        params_str = match.group(1).strip()
        if not params_str:
            return []
        
        arguments = []
        for param in self._split_parameters(params_str):
            param = param.strip()
            if not param or any(param == p for p in ['self', '&self', '&mut self']):
                continue
                
            arg_info = self._parse_parameter(param)
            if arg_info:
                arguments.append(arg_info)
        
        return arguments
    
    def _parse_parameter(self, param: str) -> Optional[Dict]:
        """Parse a parameter and extract all type components"""
        if ':' not in param:
            return None
            
        name_part, type_part = param.split(':', 1)
        name = name_part.replace('mut ', '').strip()
        type_name = type_part.strip()
        
        return {
            'name': name,
            'type': type_name,
            'type_components': self._extract_type_components(type_name),
            'is_ref': type_name.startswith('&'),
            'full_signature': param
        }
    
    def _extract_type_components(self, type_name: str) -> List[str]:
        """Extract all type names including nested generics"""
        # Remove references and mut qualifiers
        clean_type = re.sub(r'^&(?:\s*mut\s*)?', '', type_name)
        
        # Handle slices and arrays - extract the inner type
        if clean_type.startswith('[') and ']' in clean_type:
            # Extract type from [Type] or [Type; N]
            inner = clean_type[1:clean_type.rindex(']')]
            # Split by semicolon for fixed-size arrays
            inner_type = inner.split(';')[0].strip()
            return self._extract_type_components(inner_type)
        
        # Handle tuples
        if clean_type.startswith('(') and clean_type.endswith(')'):
            return self._process_tuple_types(clean_type[1:-1])
        
        # Split generic parameters
        main_type = clean_type.split('<')[0].split('::')[-1]
        components = [main_type]
        
        # Extract nested types
        if '<' in clean_type and '>' in clean_type:
            inner_types = re.search(r'<(.*)>', clean_type)
            if inner_types:
                for nested in self._split_generic_params(inner_types.group(1)):
                    components.extend(self._extract_type_components(nested))
        
        return [c for c in components if c and not c.isspace()]
    
    def _split_generic_params(self, params: str) -> List[str]:
        """Split generic parameters while handling nested generics"""
        parts = []
        current = []
        depth = 0
        
        for char in params:
            if char == ',' and depth == 0:
                parts.append(''.join(current).strip())
                current = []
            else:
                if char in '<([{':
                    depth += 1
                elif char in '>)]}':
                    depth -= 1
                current.append(char)
        
        if current:
            parts.append(''.join(current).strip())
        return parts
    
    def _process_tuple_types(self, tuple_types: str) -> List[str]:
        """Handle Rust tuple type components"""
        return [
            component.strip()
            for component in self._split_generic_params(tuple_types)
            if component.strip()
        ]
    
    def get_argument_definitions(self, file_path: str, function_signature: str) -> Dict[str, Dict]:
        """Get definitions for all argument types in a function signature"""
        # Ensure we have an absolute path for LSP
        file_path = str(Path(file_path).absolute())
        
        arguments = self.extract_function_arguments(function_signature)
        definitions = {}
        
        # Rust types to skip (primitives, stdlib, traits that LLMs already know)
        RUST_SKIP_TYPES = {
            # Primitives
            'i8', 'i16', 'i32', 'i64', 'i128', 'isize',
            'u8', 'u16', 'u32', 'u64', 'u128', 'usize',
            'f32', 'f64', 'bool', 'char', 'str',
            
            # Common stdlib (LLM already knows)
            'Vec', 'VecDeque', 'LinkedList',
            'HashMap', 'HashSet', 'BTreeMap', 'BTreeSet',
            'Box', 'Rc', 'Arc', 'Cell', 'RefCell',
            'Mutex', 'RwLock', 'Cow',
            'String', 'OsString', 'PathBuf',
            'Option', 'Result',
            
            # Traits (usually don't need extraction)
            'Iterator', 'IntoIterator', 'Clone', 'Copy',
            'Debug', 'Display', 'Default',
        }
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if self.lsp_client:
            is_new = self.lsp_client.open_document(file_path, content)
            # Only wait if this is a newly opened document
            if is_new:
                time.sleep(2)
        
        for arg in arguments:
            arg_definitions = {}
            for type_component in arg.get('type_components', []):
                # Skip known types
                if type_component in RUST_SKIP_TYPES:
                    continue
                try:
                    line, char = self._find_type_position(content, type_component)
                    if line is not None and char is not None:
                        type_def = self._get_type_definition(file_path, line, char, content)
                        if type_def:
                            arg_definitions[type_component] = type_def
                except ValueError as e:
                    # Type not found in file (might be from stdlib or external crate)
                    logger.debug(f"Type '{type_component}' not found in file (stdlib/external): {e}")
                except Exception as e:
                    logger.debug(f"Type definition lookup failed for '{type_component}': {e}")
            
            if arg_definitions:
                definitions[arg['name']] = {
                    'type': arg['type'],
                    'definitions': arg_definitions,
                    'is_ref': arg.get('is_ref', False)
                }
        
        return definitions

    def _find_type_position(self, content: str, type_name: str) :
        """Find the position of a type in the content"""
        lines = content.splitlines()
        # Skip lines that DEFINE the type (not where it's used)
        skip_patterns = [
            re.compile(rf'\b(pub\s+)?(struct|enum|trait|type)\s+{type_name}\b'),  # struct Point, enum Point, etc.
            re.compile(rf'\bimpl\b.*\bfor\b\s+{type_name}\b'),  # impl ... for Point
            re.compile(r'#\[(?:derive|macro_use).*\]'),  # attribute macros
            re.compile(r'^\s*//'),  # Line comments
        ]

        for i, line in enumerate(lines):
            if type_name not in line:
                continue
            # Skip definition lines, comments, etc.
            if any(p.search(line) for p in skip_patterns):
                continue
            try:
                char_index = line.index(type_name)
                return i, char_index
            except ValueError:
                continue

        raise ValueError(f"Can not find the use of `{type_name}`")
    
    def _get_type_definition(self, file_path: str, line: int, char: int, content: str) -> Dict:
        """Get complete type definition including implementations"""
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

        impl_blocks = []
        seen_locations = set()  # Track seen locations to avoid duplicates
        impl_results = self.lsp_client.goto_implementation(file_path, line, char)
        # Cap at 10 implementations to avoid exponential query explosion
        impl_results = impl_results[:10] if impl_results else []
        for impl in impl_results:
            impl_path = Path(impl["uri"].replace("file://", "")).as_posix()
            impl_start = impl["range"]["start"]["line"]

            if (impl_path, impl_start) in seen_locations:
                continue
            seen_locations.add((impl_path, impl_start))

            try:
                with open(impl_path, 'r', encoding='utf-8') as f:
                    imple_file_lines = f.read().splitlines()
                impl_block = self._get_definition_content(imple_file_lines, impl_start)
                impl_blocks.append({
                    'file_path': str(impl_path),
                    'code': impl_block
                })
            except Exception as e:
                print(f"Error reading implementation file: {e}")

        return {
            'type_definition': type_block,
            'implementations': impl_blocks,
            'definition_location': type_def
        }

    def _get_definition_content(self, lines: List[str], start_line: int) -> str:
        """Extract a complete code block starting from the definition line"""
        block_lines = []
        brace_count = 0
        started = False

        # Find the first line with '{'
        for i in range(start_line, len(lines)):
            if '{' in lines[i]:
                start_line = i
                break

        for i in range(start_line, len(lines)):
            line = lines[i]
            open_braces = line.count('{')
            close_braces = line.count('}')

            if open_braces > 0:
                started = True
            brace_count += open_braces - close_braces

            block_lines.append(line)

            if started and brace_count == 0:
                break

        return "\n".join(block_lines)
