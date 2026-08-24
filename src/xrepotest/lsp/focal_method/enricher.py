"""
Enricher Module

Main orchestrator for LSPRAG-style focal method enrichment.

This module provides:
- Coordination of token extraction, definition retrieval, and reference retrieval
- CFG-based filtering support for condition-aware context selection
- Integration with language-specific LSP clients
- Summary statistics generation
"""

import logging
from typing import List, Dict, Any
from pathlib import Path

from xrepotest.lsp.focal_method.token_extractor import FocalMethodTokenExtractor
from xrepotest.lsp.focal_method.retrieval import DefinitionRetriever, ReferenceRetriever

logger = logging.getLogger(__name__)


class FocalMethodEnricher:
    """
    Main orchestrator for LSPRAG-style focal method enrichment.
    Coordinates token extraction, definition retrieval, and reference retrieval.
    Now with CFG-based filtering support.
    """
    
    def __init__(self, language: str, lsp_client, repo_base_path: str = None, arg_extractor=None, use_cfg: bool = True):
        self.language = language
        self.lsp_client = lsp_client
        self.repo_base_path = repo_base_path
        self.arg_extractor = arg_extractor  # Reuse existing language-specific extractor
        self.token_extractor = FocalMethodTokenExtractor(language)
        self.definition_retriever = DefinitionRetriever(lsp_client, repo_base_path, arg_extractor)
        self.reference_retriever = ReferenceRetriever(lsp_client)
        self.use_cfg = use_cfg
        
        # Initialize CFG components if enabled
        self.cfg_builder = None
        self.path_collector = None
        
        if self.use_cfg:
            from xrepotest.lsp.cfg.builder_factory import CFGBuilderFactory
            from xrepotest.lsp.cfg.path import PathCollector
            
            # Get tree-sitter parser from token_extractor
            parser = self.token_extractor.parser
            self.cfg_builder = CFGBuilderFactory.create_builder(language, parser)
            self.path_collector = PathCollector(language)
            logger.info(f"CFG-based filtering enabled for {language}")
    
    def enrich_focal_method(self, function_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich a function with focal method context.
        
        Args:
            function_data: Dictionary with function info (from xrepotest format)
            
        Returns:
            Enriched dictionary with focal_method_analysis section
        """
        focal_code = function_data.get('focal_code', '')
        file_path = function_data.get('file_path', '')
        file_content = function_data.get('file_content', '')
        start_line = function_data.get('function_component', {}).get('start_line', 0)
        
        if not focal_code or not file_path:
            logger.warning("Missing focal_code or file_path")
            return {}
        
        # Convert file_path to absolute if it's relative
        if not Path(file_path).is_absolute() and self.repo_base_path:
            # file_path examples:
            #   Standard: "Rust-master/src/file.rs"  
            #   Crate: "burn-main/crates/burn-core/src/file.rs"
            # repo_base_path examples:
            #   Standard: "/path/to/rust/Rust-master"
            #   Crate: "/path/to/rust/burn-main/crates/burn-core"
            
            # Extract the relative portion of repo_base_path after the language folder
            repo_path_parts = str(self.repo_base_path).split('/')
            lang_idx = None
            for i, part in enumerate(repo_path_parts):
                if part in ['rust', 'go', 'julia', 'ruby', 'php']:
                    lang_idx = i
                    break
            
            if lang_idx is not None and lang_idx + 1 < len(repo_path_parts):
                # Get everything after the language folder (e.g., "burn-main/crates/burn-core")
                repo_relative_path = '/'.join(repo_path_parts[lang_idx + 1:])
                # If file_path starts with this, strip it
                if file_path.startswith(repo_relative_path + '/'):
                    relative_path = file_path[len(repo_relative_path) + 1:]
                    file_path = str(Path(self.repo_base_path) / relative_path)
                else:
                    # Fallback: just remove first component
                    parts = file_path.split('/', 1)
                    file_path = str(Path(self.repo_base_path) / (parts[1] if len(parts) > 1 else file_path))
            else:
                # Fallback: just remove first component
                parts = file_path.split('/', 1)
                if len(parts) > 1:
                    file_path = str(Path(self.repo_base_path) / parts[1])
                else:
                    file_path = str(Path(self.repo_base_path) / file_path)
        else:
            file_path = str(Path(file_path).absolute())
        
        # Step 1: Extract tokens
        # Detect if start_line is 0-indexed or 1-indexed by comparing with file content
        # xrepotest dataset has inconsistent indexing across languages:
        #   - Go:    0-indexed (start_line points directly to array index)
        #   - Rust:  1-indexed (start_line - 1 = array index)
        #   - Ruby:  1-indexed (start_line - 1 = array index)
        #   - PHP:   1-indexed (start_line - 1 = array index)
        #   - Julia: 1-indexed (start_line - 1 = array index)
        # LSP specification requires 0-indexed positions, so we detect and convert accordingly.
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                file_lines = f.readlines()
            
            focal_first_line = focal_code.split('\n')[0].strip()
            
            # Check if start_line is already 0-indexed (matches directly) - Go case
            if start_line < len(file_lines) and file_lines[start_line].strip() == focal_first_line:
                start_line_0indexed = start_line
                logger.debug(f"Detected 0-indexed start_line={start_line} (Go convention, already correct for LSP)")
            # Check if start_line is 1-indexed (need to subtract 1) - Rust/Ruby/PHP/Julia case
            elif start_line > 0 and start_line - 1 < len(file_lines) and file_lines[start_line - 1].strip() == focal_first_line:
                start_line_0indexed = start_line - 1
                logger.debug(f"Detected 1-indexed start_line={start_line}, converted to {start_line_0indexed} for LSP (Rust/Ruby/PHP/Julia convention)")
            else:
                # Fallback: assume 1-indexed (most common) if detection fails
                start_line_0indexed = max(0, start_line - 1)
                logger.warning(
                    f"Could not match focal method first line at start_line={start_line} or {start_line-1}. "
                    f"Expected: '{focal_first_line[:50]}...'. "
                    f"Assuming 1-indexed convention (using {start_line_0indexed})."
                )
        except Exception as e:
            # On error, assume 1-indexed (most common case)
            start_line_0indexed = max(0, start_line - 1)
            logger.warning(f"Error detecting start_line indexing: {e}. Assuming 1-indexed convention (using {start_line_0indexed})")
        
        # Skip extremely large functions that can cause hangs
        code_size = len(focal_code)
        if code_size > 10000:
            logger.warning(f"Skipping function with {code_size} characters (too large, may cause hang)")
            return {
                'function_name': function_data.get('function_name', 'unknown'),
                'error': 'Function too large (>10K chars)',
                'code_size': code_size
            }
        
        logger.debug(f"Extracting tokens from {code_size} character function...")
        tokens = self.token_extractor.extract_tokens(focal_code, file_path, start_line_0indexed)
        logger.info(f"Extracted {len(tokens)} tokens from focal method")
        
        # Step 1.5: CFG-based filtering (NEW)
        cfg_info = {}
        if self.use_cfg and self.cfg_builder and self.path_collector:
            try:
                logger.debug("Building CFG for focal method...")
                # PHP requires <?php tag for parsing
                cfg_code = focal_code
                if self.language == 'php' and not focal_code.strip().startswith('<?php'):
                    cfg_code = '<?php\n' + focal_code
                cfg = self.cfg_builder.build_from_code(cfg_code)
                logger.info("✓ CFG built successfully")
                
                logger.debug("Collecting CFG paths...")
                paths = self.path_collector.collect(cfg.entry)
                conditions = self.path_collector.get_unique_conditions()
                logger.info(f"CFG analysis: {len(paths)} paths, {len(conditions)} unique conditions")
                
                # Enable CFG filtering in classifier
                self.token_extractor.classifier.enable_cfg_filtering(conditions)
                
                # Re-classify tokens based on CFG
                filtered_tokens = []
                for token in tokens:
                    token_word = token['word']
                    logger.debug(f"Checking token '{token_word}' (type: {token.get('type')})")
                    token['need_definition'] = self.token_extractor.classifier.cfg_based_is_definition_helpful(token)
                    token['need_references'] = self.token_extractor.classifier.cfg_based_is_reference_helpful(token)
                    
                    # Add condition metadata
                    related_conds = [c.condition for c in conditions if token_word in c.dependencies]
                    token['related_conditions'] = related_conds
                    
                    if token['need_definition'] or token['need_references']:
                        logger.debug(f"  -> Token '{token_word}' passed CFG filtering")
                        filtered_tokens.append(token)
                    else:
                        logger.debug(f"  -> Token '{token_word}' filtered out (not in conditions or skipped)")
                
                original_count = len(tokens)
                tokens = filtered_tokens
                reduction_pct = ((original_count - len(tokens)) / original_count * 100) if original_count > 0 else 0
                logger.info(f"CFG filtering: {len(tokens)} tokens remain (in conditions), {reduction_pct:.1f}% reduction")
                
                # Store CFG info for output
                cfg_info = {
                    'total_paths': len(paths),
                    'conditions': [c.condition for c in conditions],
                    'original_token_count': original_count,
                    'filtered_token_count': len(tokens),
                    'reduction_percentage': round(reduction_pct, 1)
                }
            except Exception as e:
                logger.warning(f"CFG analysis failed: {e}, continuing without CFG filtering")
                import traceback
                logger.debug(traceback.format_exc())
        
        # Step 2: Retrieve definitions for helpful tokens
        enriched_tokens = []
        definitions_retrieved = 0
        references_retrieved = 0
        
        # Log how many tokens need definitions/references after filtering
        tokens_needing_definitions = sum(1 for t in tokens if t.get('need_definition', False))
        tokens_needing_references = sum(1 for t in tokens if t.get('need_references', False))
        if tokens_needing_definitions > 0 or tokens_needing_references > 0:
            logger.info(f"Requesting LSP: {tokens_needing_definitions} definitions, {tokens_needing_references} references")
        
        for token in tokens:
            enriched_token = token.copy()
            
            if token.get('need_definition', False):
                try:
                    definition = self.definition_retriever.get_definition(
                        file_path, 
                        token['line'], 
                        token['char'],
                        file_content,
                        token['word']
                    )
                    if definition:
                        enriched_token['definition'] = definition
                        definitions_retrieved += 1
                except TimeoutError as e:
                    logger.warning(f"Timeout getting definition for {token['word']}: {e}")
                    # Skip this token and continue with others
                    enriched_token['definition_error'] = 'timeout'
                except BrokenPipeError as e:
                    logger.error(f"LSP connection broken getting definition for {token['word']}: {e}")
                    # LSP is dead, stop trying to get more definitions
                    enriched_token['definition_error'] = 'broken_pipe'
                    enriched_tokens.append(enriched_token)
                    break
                except Exception as e:
                    logger.warning(f"Failed to get definition for {token['word']}: {e}")
                    enriched_token['definition_error'] = str(e)
            
            if token.get('need_references', False):
                try:
                    references = self.reference_retriever.get_references(
                        file_path,
                        token['line'],
                        token['char'],
                        token['word'],
                        max_examples=2
                    )
                    if references:
                        enriched_token['references'] = references
                        references_retrieved += 1
                except TimeoutError as e:
                    logger.warning(f"Timeout getting references for {token['word']}: {e}")
                    enriched_token['references_error'] = 'timeout'
                except BrokenPipeError as e:
                    logger.error(f"LSP connection broken getting references for {token['word']}: {e}")
                    enriched_token['references_error'] = 'broken_pipe'
                    enriched_tokens.append(enriched_token)
                    break
                except Exception as e:
                    logger.warning(f"Failed to get references for {token['word']}: {e}")
                    enriched_token['references_error'] = str(e)
            
            enriched_tokens.append(enriched_token)
        
        logger.info(f"Retrieved {definitions_retrieved} definitions and {references_retrieved} reference sets")
        
        # Log success rate metrics
        tokens_needing_definitions = sum(1 for t in tokens if t.get('need_definition', False))
        tokens_needing_references = sum(1 for t in tokens if t.get('need_references', False))
        
        if tokens_needing_definitions > 0:
            def_success_rate = (definitions_retrieved / tokens_needing_definitions) * 100
            logger.info(f"Definition retrieval success rate: {def_success_rate:.1f}% ({definitions_retrieved}/{tokens_needing_definitions})")
            if def_success_rate < 50:
                logger.warning("⚠️  Low definition success rate - check LSP connection and indexing")
        
        if tokens_needing_references > 0:
            ref_success_rate = (references_retrieved / tokens_needing_references) * 100
            logger.info(f"Reference retrieval success rate: {ref_success_rate:.1f}% ({references_retrieved}/{tokens_needing_references})")
        
        # Step 3: Build summary
        summary = self._build_summary(enriched_tokens)
        
        result = {
            'tokens': enriched_tokens,
            'summary': summary
        }
        
        # Add CFG info if available
        if cfg_info:
            result['cfg_info'] = cfg_info
        
        return result
    
    def _build_summary(self, tokens: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build summary statistics for focal method analysis"""
        total_tokens = len(tokens)
        tokens_with_definitions = sum(1 for t in tokens if 'definition' in t)
        tokens_with_references = sum(1 for t in tokens if 'references' in t)
        
        # Extract key types and functions
        key_types = list(set(
            t['word'] for t in tokens 
            if t.get('type') in ['type', 'class', 'struct', 'interface']
            and 'definition' in t
        ))
        
        key_functions = list(set(
            t['word'] for t in tokens
            if t.get('type') in ['function', 'method']
            and 'definition' in t
        ))
        
        return {
            'total_tokens': total_tokens,
            'tokens_with_definitions': tokens_with_definitions,
            'tokens_with_references': tokens_with_references,
            'key_types': key_types[:10],  # Limit to top 10
            'key_functions': key_functions[:10]
        }
