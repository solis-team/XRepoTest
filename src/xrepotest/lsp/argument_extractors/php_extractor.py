import re
import logging
from typing import List, Dict, Optional
from pathlib import Path
from xrepotest.lsp.argument_extractors.base_extractor import BaseArgumentExtractor

logger = logging.getLogger(__name__)


class PHPArgumentExtractor(BaseArgumentExtractor):
    """PHP-specific argument extractor."""

    def get_language(self) -> str:
        """Return PHP language identifier."""
        return "php"
        
    def extract_function_arguments(self, function_signature: str) -> List[Dict]:
        """Extract argument names and types from PHP function signature"""
        # Normalize whitespace and remove comments
        signature = self._normalize_whitespace(function_signature)
        signature = re.sub(r'//.*?$', '', signature, flags=re.MULTILINE)
        signature = re.sub(r'/\*.*?\*/', '', signature, flags=re.DOTALL)
        
        # Remove visibility modifiers and return type
        signature = re.sub(r'^\s*(public|private|protected|static|final|abstract)\s+', '', signature)
        signature = re.sub(r':\s*\??\w+\s*$', '', signature)
        
        # Extract parameters from function name(params)
        # Handle class-qualified names: MyClass::method, MyClass->method, or simple function names
        match = re.search(r'function\s+(?:[\w:>-]+)\s*\((.*?)\)', signature)
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
        """Parse a PHP parameter
        Formats: $name, Type $name, Type $name = default, ?Type $name, Type ...$name"""
        # Remove default values
        if '=' in param:
            param = param.split('=')[0].strip()
        
        # Check for variadic
        is_variadic = '...' in param
        param = param.replace('...', '')
        
        # Parse type hint and variable name
        parts = param.split()
        
        if len(parts) == 1:
            # No type hint: $name
            var_name = parts[0].lstrip('$')
            type_name = 'mixed'
        else:
            # Has type hint: Type $name or ?Type $name
            type_part = ' '.join(parts[:-1])
            var_name = parts[-1].lstrip('$')
            
            # Handle nullable types
            type_name = type_part.lstrip('?').strip()
        
        return {
            'name': var_name,
            'type': type_name,
            'type_components': self._extract_type_components(type_name),
            'is_variadic': is_variadic,
            'full_signature': param
        }
    
    def _extract_type_components(self, type_name: str) -> List[str]:
        """Extract type names from PHP type hints"""
        # Handle union types (PHP 8+): Type1|Type2
        if '|' in type_name:
            types = [t.strip() for t in type_name.split('|')]
            return [t for t in types if t]
        
        # Handle array types
        if type_name == 'array' or type_name.endswith('[]'):
            return []
        
        # Remove namespace separators and get the class name
        if '\\' in type_name:
            type_name = type_name.split('\\')[-1]
        
        return [type_name] if type_name else []
    
    def get_argument_definitions(self, file_path: str, function_signature: str) -> Dict[str, Dict]:
        """Get definitions for all argument types using goto_type_definition on variable names"""
        # Ensure absolute path
        file_path = str(Path(file_path).absolute())
        
        arguments = self.extract_function_arguments(function_signature)
        definitions = {}
        
        # Use centralized type filtering from TokenClassifier
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if self.lsp_client:
                self.lsp_client.open_document(file_path, content)
            
            for arg in arguments:
                arg_name = arg['name']
                arg_type = arg.get('type', '')
                
                # Skip if no type or builtin type
                if not arg_type or arg_type.strip('?|\\') in self.builtin_types:
                    continue
                
                # Try to get type definition using goto_type_definition on variable name
                try:
                    line, char = self._find_variable_position(content, function_signature, arg_name)
                    if line is not None and char is not None:
                        type_def = self._get_type_definition_from_variable(file_path, line, char)
                        if type_def:
                            definitions[arg_name] = {
                                'type': arg_type,
                                'definitions': {arg_type: type_def}
                            }
                except Exception as e:
                    logger.debug(f"Variable position not found or LSP query failed: {e}")
        
        except Exception as e:
            logger.error(f"Error in PHP get_argument_definitions: {e}")
            import traceback
            traceback.print_exc()
        
        return definitions
    
    def _find_variable_position(self, content: str, signature: str, var_name: str) -> tuple:
        """Find the position of a variable name in the function signature."""
        import re
        
        # PHP variables start with $
        if not var_name.startswith('$'):
            var_name = '$' + var_name
        
        # Find the signature in the content
        sig_start = content.find(signature)
        if sig_start == -1:
            # Try normalizing whitespace
            sig_normalized = ' '.join(signature.split())
            content_normalized = ' '.join(content.split())
            sig_start = content_normalized.find(sig_normalized)
            if sig_start == -1:
                return None, None
        
        # Find the variable name within the signature
        param_pattern = rf'\{re.escape(var_name)}\b'
        match = re.search(param_pattern, signature)
        if not match:
            return None, None
        
        # Calculate absolute position in content
        var_pos = sig_start + match.start()
        
        # Convert to line and column
        before_var = content[:var_pos]
        line = before_var.count('\n')
        col = len(before_var) - before_var.rfind('\n') - 1
        
        return line, col
    
    def _get_type_definition_from_variable(self, file_path: str, line: int, char: int) -> Dict:
        """Get type definition by calling goto_type_definition on a variable name."""
        if not self.lsp_client:
            return None
        
        # Use goto_type_definition on the variable name
        type_defs = self.lsp_client.goto_type_definition(file_path, line, char)
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
        end_line = type_def["range"]["end"]["line"]

        try:
            with open(def_path, 'r', encoding='utf-8') as f:
                def_lines = f.readlines()
            # Read a few lines around the definition
            context_start = max(0, start_line - 1)
            context_end = min(len(def_lines), end_line + 10)
            type_block = ''.join(def_lines[context_start:context_end]).strip()
        except Exception as e:
            logger.error(f"Error reading definition file {def_path}: {e}")
            type_block = ""

        return {
            'type_definition': type_block,
            'definition_location': type_def
        }
    
