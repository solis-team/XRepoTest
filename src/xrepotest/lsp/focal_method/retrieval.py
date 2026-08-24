"""
Retrieval Module

Retrieve definitions and usage examples for tokens using LSP.

This module provides:
- Definition retrieval with LSP goto_definition queries
- Reference retrieval with LSP find_references queries
- Code extraction from LSP location ranges
- Caching to avoid duplicate queries
"""

import logging
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class DefinitionRetriever:
    """Retrieve definition code for tokens using LSP"""
    
    def __init__(self, lsp_client, repo_base_path: str = None, arg_extractor=None):
        self.lsp_client = lsp_client
        self.repo_base_path = repo_base_path  # Base path for repository
        self.arg_extractor = arg_extractor  # Language-specific argument extractor
        self.cache = {}  # Cache definitions to avoid duplicate queries
        self.opened_documents = set()  # Track opened documents
    
    def get_definition(self, file_path: str, line: int, char: int, 
                       file_content: str, token_word: str) -> Optional[Dict[str, Any]]:
        """
        Query LSP for definition and extract code.
        
        Args:
            file_path: Path to the file
            line: Line number (0-indexed)
            char: Character position (0-indexed)
            file_content: Full file content
            token_word: The token text for caching
            
        Returns:
            Dictionary with definition info or None
        """
        cache_key = f"{file_path}:{line}:{char}:{token_word}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            # Open document in LSP if not already opened
            if file_path not in self.opened_documents:
                self.lsp_client.open_document(file_path, file_content)
                self.opened_documents.add(file_path)
            
            # Query LSP directly for token definitions with retry for transient errors
            max_retries = 1
            definition_result = None
            
            for attempt in range(max_retries + 1):
                try:
                    definition_result = self.lsp_client.goto_definition(file_path, line, char)
                    break  # Success, exit retry loop
                except BrokenPipeError:
                    if attempt < max_retries:
                        logger.debug(f"BrokenPipeError on attempt {attempt + 1}, retrying after brief delay...")
                        time.sleep(0.5)
                    else:
                        raise  # Re-raise if final attempt failed
            
            if not definition_result:
                logger.debug(f"No definition found for {token_word} at {file_path}:{line}:{char}")
                return None
            
            # Convert LSP response to expected format
            # goto_definition returns a list of locations directly
            formatted_result = {
                'definitions': []
            }
            
            for loc in definition_result:
                # LSP returns: {'uri': 'file://...', 'range': {...}}
                uri = loc.get('uri', '')
                file_path_from_uri = uri.replace('file://', '')
                
                # If path is relative or missing repo base, prepend it
                if self.repo_base_path and not file_path_from_uri.startswith(self.repo_base_path):
                    # Handle cases like '/Go-master/...' -> '/workspace/.../Go-master/...'
                    if file_path_from_uri.startswith('/'):
                        # Extract relative part after first directory
                        parts = file_path_from_uri.lstrip('/').split('/', 1)
                        if len(parts) > 1:
                            file_path_from_uri = str(Path(self.repo_base_path) / parts[1])
                        else:
                            file_path_from_uri = str(Path(self.repo_base_path) / parts[0])
                    else:
                        file_path_from_uri = str(Path(self.repo_base_path) / file_path_from_uri)
                
                formatted_result['definitions'].append({
                    'file_path': file_path_from_uri,
                    'range': loc.get('range', {})
                })
            
            # Extract definition code
            def_info = self._extract_definition_code(formatted_result, file_path, file_content)
            
            self.cache[cache_key] = def_info
            return def_info
            
        except Exception as e:
            logger.warning(f"Error getting definition for {token_word}: {e}")
            return None
    
    def _extract_definition_code(self, definition_result: Dict, 
                                 source_file: str, 
                                 file_content: str) -> Optional[Dict[str, Any]]:
        """Extract code snippet from definition result using language-specific extractors"""
        if not definition_result or 'definitions' not in definition_result:
            return None
        
        definitions = definition_result['definitions']
        if not definitions:
            return None
        
        # Use first definition
        first_def = definitions[0]
        def_file = first_def.get('file_path', source_file)
        def_range = first_def.get('range', {})
        start_line = def_range.get('start', {}).get('line', 0)
        
        # Read definition file if different
        if def_file != source_file:
            try:
                with open(def_file, 'r', encoding='utf-8') as f:
                    def_content = f.read()
            except Exception as e:
                logger.debug(f"Could not read definition file {def_file}: {e}")
                return None
        else:
            def_content = file_content
        
        # Use language-specific _get_definition_content if available (extracts full definition with braces)
        # This properly handles cases where LSP only returns the start position
        if self.arg_extractor and hasattr(self.arg_extractor, '_get_definition_content'):
            try:
                def_lines = def_content.splitlines()
                code = self.arg_extractor._get_definition_content(def_lines, start_line)
            except Exception as e:
                logger.debug(f"Error using language-specific extractor: {e}, falling back to range extraction")
                code = self._extract_code_from_range(def_content, def_range)
        else:
            # Fallback: use range-based extraction
            code = self._extract_code_from_range(def_content, def_range)
        
        return {
            'file_path': def_file,
            'range': def_range,
            'code': code
        }
    
    def _extract_code_from_range(self, content: str, range_dict: Dict) -> str:
        """Extract code from content using LSP range (0-indexed positions)"""
        if not range_dict:
            return ""
        
        start = range_dict.get('start', {})
        end = range_dict.get('end', {})
        start_line = start.get('line', 0)
        start_char = start.get('character', 0)
        end_line = end.get('line', 0)
        end_char = end.get('character', 0)
        
        lines = content.split('\n')
        if start_line >= len(lines):
            return ""
        
        # Check if this points to an import statement - if so, skip it
        # Go: import "package" or import ( ... )
        # Python: import module / from module import ...
        # Rust: use crate::module;
        first_line = lines[start_line].strip()
        if (first_line.startswith('import ') or 
            first_line.startswith('from ') or 
            first_line.startswith('use ') or
            (first_line.startswith('"') and start_char > 0 and 'import' in lines[start_line][:start_char])):
            # This is an import statement, return empty to signal it should be skipped
            return ""
        
        # Single line: extract character range
        if start_line == end_line:
            line_content = lines[start_line]
            # Extract from start_char to end_char
            return line_content[start_char:end_char] if end_char > start_char else line_content
        
        # Multi-line: extract with character precision on first and last lines
        extracted = []
        for i in range(start_line, min(end_line + 1, len(lines))):
            if i == start_line:
                # First line: extract from start_char to end
                extracted.append(lines[i][start_char:])
            elif i == end_line:
                # Last line: extract from beginning to end_char
                extracted.append(lines[i][:end_char])
            else:
                # Middle lines: extract completely
                extracted.append(lines[i])
        
        return '\n'.join(extracted)


class ReferenceRetriever:
    """Retrieve usage examples for tokens using LSP"""
    
    def __init__(self, lsp_client):
        self.lsp_client = lsp_client
        self.cache = {}
        self.opened_documents = set()  # Track opened documents
    
    def get_references(self, file_path: str, line: int, char: int,
                      token_word: str, max_examples: int = 3) -> List[Dict[str, Any]]:
        """
        Query LSP for references and extract usage examples.
        
        Args:
            file_path: Path to the file
            line: Line number (0-indexed)
            char: Character position (0-indexed)
            token_word: The token text
            max_examples: Maximum number of examples to return
            
        Returns:
            List of reference examples
        """
        cache_key = f"{file_path}:{line}:{char}:{token_word}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            # Note: Document should already be opened by DefinitionRetriever
            # But check anyway for safety
            
            # Query LSP for references
            if not hasattr(self.lsp_client, 'find_references'):
                logger.debug("LSP client doesn't support find_references yet")
                return []
            
            references_result = self.lsp_client.find_references(file_path, line, char)
            
            if not references_result or 'references' not in references_result:
                return []
            
            # Process references
            examples = self._process_references(
                references_result['references'], 
                file_path,
                max_examples
            )
            
            self.cache[cache_key] = examples
            return examples
            
        except Exception as e:
            logger.warning(f"Error getting references for {token_word}: {e}")
            return []
    
    def _process_references(self, references: List[Dict], 
                           source_file: str,
                           max_examples: int) -> List[Dict[str, Any]]:
        """Process and filter reference results"""
        examples = []
        
        # Filter out test files and sort by relevance
        non_test_refs = [
            ref for ref in references
            if not self._is_test_file(ref.get('file_path', ''))
        ]
        
        # Limit to max_examples
        for ref in non_test_refs[:max_examples]:
            ref_file = ref.get('file_path', source_file)
            ref_range = ref.get('range', {})
            
            # Skip if file doesn't exist (may be outside current repo)
            try:
                if not Path(ref_file).exists():
                    logger.debug(f"Skipping reference in non-existent file: {ref_file}")
                    continue
                
                with open(ref_file, 'r', encoding='utf-8') as f:
                    ref_content = f.read()
                
                # Extract context around reference (e.g., enclosing function)
                code = self._extract_reference_context(ref_content, ref_range)
                
                examples.append({
                    'file_path': ref_file,
                    'range': ref_range,
                    'code': code
                })
            except Exception as e:
                logger.debug(f"Could not process reference in {ref_file}: {e}")
                continue
        
        return examples
    
    def _is_test_file(self, file_path: str) -> bool:
        """Check if file is a test file"""
        test_patterns = ['_test.', 'test_', '/test/', '/tests/', 'Test.', 'Spec.']
        file_path_lower = file_path.lower()
        return any(pattern.lower() in file_path_lower for pattern in test_patterns)
    
    def _extract_reference_context(self, content: str, range_dict: Dict) -> str:
        """Extract contextual code around reference"""
        # For now, extract the line and a few lines around it
        start_line = range_dict.get('start', {}).get('line', 0)
        context_lines = 5  # Lines before and after
        
        lines = content.split('\n')
        context_start = max(0, start_line - context_lines)
        context_end = min(len(lines), start_line + context_lines + 1)
        
        return '\n'.join(lines[context_start:context_end])
