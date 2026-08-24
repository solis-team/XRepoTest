"""
LSP-based Function Argument Definition Extractor

This script uses custom LSP clients (go_lsp, rust_lsp, ruby_lsp, php_lsp, julia_lsp) 
to extract function argument definitions from Go, Rust, Ruby, PHP, and Julia codebases. 
It processes JSONL files in the input directory and creates enriched versions with 
type definitions retrieved from LSP language servers.

Extended with LSPRAG-style focal method enrichment for comprehensive context extraction.
"""

import json
import logging
import signal
import time
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
from typing import List, Dict, Any
from collections import defaultdict

# Import LSP clients
from xrepotest.lsp.lsp_client import (
    GoLSPClient,
    RustLSPClient,
    RubyLSPClient,
    PHPLSPClient,
    JuliaLSPClient,
)

# Import argument extractors
from xrepotest.lsp.argument_extractors import (
    GoArgumentExtractor,
    RustArgumentExtractor,
    RubyArgumentExtractor,
    PHPArgumentExtractor,
    JuliaArgumentExtractor,
)

# Import focal method enricher
from xrepotest.lsp.focal_method import FocalMethodEnricher
from xrepotest.paths import get_lsp_enriched_dir
from xrepotest.lsp.config import LSP_TIMEOUT_SECONDS

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Seconds allowed per function before the LSP extraction is aborted.
_LSP_TIMEOUT_SECONDS = LSP_TIMEOUT_SECONDS


def _lsp_timeout_handler(*_args):
    raise TimeoutError(f"Function extraction timed out after {_LSP_TIMEOUT_SECONDS} seconds")


class ArgumentExtractor:
    """Extract function argument definitions using custom LSP clients."""
    
    LANGUAGE_CONFIG = {
        'go': {
            'lsp_client_class': GoLSPClient,
            'arg_extractor_class': GoArgumentExtractor
        },
        'rust': {
            'lsp_client_class': RustLSPClient,
            'arg_extractor_class': RustArgumentExtractor
        },
        'ruby': {
            'lsp_client_class': RubyLSPClient,
            'arg_extractor_class': RubyArgumentExtractor
        },
        'php': {
            'lsp_client_class': PHPLSPClient,
            'arg_extractor_class': PHPArgumentExtractor
        },
        'julia': {
            'lsp_client_class': JuliaLSPClient,
            'arg_extractor_class': JuliaArgumentExtractor
        }
    }
    
    # List of repositories that should be fully enriched via LSP
    # Other repositories will be saved with placeholder data to save time
    PROCESS_REPOS = [
        # Go
        'client_golang', 'zap',
        # Julia
        'dataframes.jl',
        # PHP
        'flysystem', 'monolog', 'PHPMailer', 'uuid',
        # Ruby
        'grape', 'hanami', 'rom', 'shoryuken',
        # Rust
        'hyper', 'nom', 'uuid'
    ]

    def __init__(self, workspace_root: Path, limit: int = None, enable_focal_method: bool = True, use_cfg: bool = True):
        """
        Initialize the extractor.
        
        Args:
            workspace_root: Root directory of the workspace
            limit: Maximum number of functions to process per language (None = all)
            enable_focal_method: Enable LSPRAG-style focal method enrichment
            use_cfg: Enable CFG-based token filtering (only applies if enable_focal_method=True)
        """
        self.workspace_root = workspace_root
        self.limit = limit
        self.enable_focal_method = enable_focal_method
        self.use_cfg = use_cfg
        self._run_id = datetime.now(timezone.utc).isoformat()
        
    def extract_for_language(self, lang_name: str, input_file: Path = None, repo_base: Path = None):
        """
        Extract argument definitions for a specific language.
        
        Args:
            lang_name: Language identifier
            input_file: Path to input JSONL file (optional, defaults to standard location)
            repo_dir: Path to repository base directory (optional, defaults to standard location)
        """
        if lang_name not in self.LANGUAGE_CONFIG:
            logger.error(f"Language {lang_name} not supported")
            return
            
        config = self.LANGUAGE_CONFIG[lang_name]
        
        # Determine paths with fallbacks
        from xrepotest.paths import get_repo_data_dir, get_project_root
        
        if input_file is None:
            # Fallback to standard location in src/xrepotest/environments/xrepotest/
            input_file = get_project_root() / "src" / "xrepotest" / "environments" / "xrepotest" / f"{lang_name}_functions.jsonl"
            
        if repo_base is None:
            # Fallback to standard location in repo_data/{lang}
            repo_base = get_repo_data_dir() / lang_name

        jsonl_path = Path(input_file)
        repo_base = Path(repo_base)
        
        # Save enriched files to canonical unified LSP output folder
        results_dir = get_lsp_enriched_dir()
        results_dir.mkdir(parents=True, exist_ok=True)
        out_path = results_dir / f"{jsonl_path.stem}_enriched.jsonl"
        
        # Ensure we're reading the base input file, not an enriched version
        if '_enriched' in jsonl_path.name:
            logger.error(f"Invalid input file: {jsonl_path.name} (enriched files cannot be used as input)")
            return
        
        if not jsonl_path.exists():
            logger.error(f"JSONL file not found: {jsonl_path}")
            return
        
        logger.info(f"Processing {lang_name.upper()} functions from {jsonl_path}")
        logger.info(f"Using repository base: {repo_base}")
        
        # Load all functions
        functions = self._load_jsonl(jsonl_path)
        
        # Resume from previous run if enriched file exists
        already_processed = {}
        if out_path.exists():
            logger.info(f"📄 Found existing {out_path.name} - resuming from checkpoint")
            enriched_funcs = self._load_jsonl(out_path)
            # Track processed functions by task_id (primary) or unique key
            for func in enriched_funcs:
                task_id = func.get('task_id')
                if task_id is not None:
                    already_processed[task_id] = func
                else:
                    key = (func['file_path'], func['function_name'])
                    already_processed[key] = func
            logger.info(f"✓ Already processed: {len(already_processed)} functions")
        
        # Filter out already processed functions
        remaining_functions = []
        for func in functions:
            task_id = func.get('task_id')
            key = (func['file_path'], func['function_name'])
            if task_id is not None:
                if task_id not in already_processed:
                    remaining_functions.append(func)
            elif key not in already_processed:
                remaining_functions.append(func)
        
        if not remaining_functions:
            logger.info(f"✓ {lang_name.upper()} already complete - all {len(functions)} functions processed")
            return
        
        logger.info(f"📊 Total: {len(functions)} functions, Remaining: {len(remaining_functions)} functions")
        
        if self.limit:
            remaining_functions = remaining_functions[:self.limit]
            logger.info(f"Limited to {self.limit} remaining functions")
        
        # Group remaining functions by repository (or crate for Rust)
        repo_functions = self._group_by_repo(remaining_functions)
        logger.info(f"Found {len(repo_functions)} repositories to process")
        
        # Process each repository/crate
        for repo_name, repo_funcs in repo_functions.items():
            repo_path = repo_base / repo_name
            if not repo_path.exists():
                logger.warning(f"Repository path not found: {repo_path}")
                # Add unprocessed functions as errors
                for func in repo_funcs:
                    err_func = self._mark_as_error(func, lang_name, repo_name, "Repository not found")
                    self._append_jsonl(out_path, err_func)
                continue
                
            logger.info(f"Processing repository: {repo_name} ({len(repo_funcs)} functions)")
            self._process_repository(
                repo_path, 
                repo_funcs,
                config,
                lang_name,
                output_file=out_path
            )
            logger.info(f"✓ Finished processing repository: {repo_name}")
        
        # Final cleanup: deduplicate and sort
        logger.info(f"Cleaning up {out_path.name}...")
        self._deduplicate_file(out_path)
        
        final_count = len(self._load_jsonl(out_path))
        logger.info(
            f"Completed {lang_name.upper()}: {final_count} total functions "
            f"→ {out_path}"
        )
        
    def _process_repository(
        self, 
        repo_path: Path,
        functions: List[Dict],
        config: Dict,
        lang_name: str,
        output_file: Path = None
    ) -> List[Dict]:
        """Process all functions in a single repository using LSP client."""
        repo_name = repo_path.name
        
        # Check if we should skip full LSP extraction for this repository
        if repo_name not in self.PROCESS_REPOS:
            logger.info(f"⏭ Skipping full LSP extraction for {repo_name} (not in PROCESS_REPOS)")
            for func in functions:
                out_func = deepcopy(func)
                out_func.setdefault("function_component", {})
                out_func["function_component"]["argument_definitions_lsp"] = []
                out_func.setdefault("lsp_extraction", {})
                out_func["lsp_extraction"].update({
                    "run_id": self._run_id,
                    "language": lang_name,
                    "repository": repo_name,
                    "status": "ok",
                    "focal_method_enriched": False,
                    "skipped": True
                })
                self._append_jsonl(output_file, out_func)
            return []

        lsp_client = None
        processed_count = 0
        
        # Performance tracking for LSP restart logic
        function_times = []
        repo_start_time = time.time()
        lsp_restarts = 0
        MAX_RESTARTS = 100  # Increased for Rust's aggressive restart strategy (every 5 functions)
        functions_since_restart = 0
        
        try:
            # Initialize LSP client for this repository
            lsp_client_class = config['lsp_client_class']
            arg_extractor_class = config['arg_extractor_class']
            
            logger.info(f"Starting {lang_name} LSP server for {repo_path.name}...")
            lsp_client = lsp_client_class(str(repo_path))
            lsp_client.start()
            logger.info(f"LSP server ready for {repo_path.name} (waiting for indexing...)")
            
            # Create argument extractor with LSP client
            arg_extractor = arg_extractor_class(lsp_client=lsp_client)
            
            # Create focal method enricher if enabled
            focal_enricher = None
            if self.enable_focal_method:
                try:
                    # Pass the arg_extractor to reuse language-specific methods
                    focal_enricher = FocalMethodEnricher(lang_name, lsp_client, str(repo_path), arg_extractor, use_cfg=self.use_cfg)
                    logger.info(f"Focal method enrichment enabled for {lang_name} (CFG={self.use_cfg})")
                except Exception as e:
                    logger.warning(f"Could not create focal enricher for {lang_name}: {e}")
            
            signal.signal(signal.SIGALRM, _lsp_timeout_handler)

            # Process each function
            for idx, func in enumerate(functions, 1):
                func_name = func.get('function_name', '?')
                func_start_time = time.time()
                
                # Log progress every 5 functions
                if idx % 5 == 1 or idx == len(functions):
                    logger.info(f"Processing function {idx}/{len(functions)}: {func_name}")
                
                try:
                    # Use language-specific extraction timeout from LSP config
                    extraction_timeout = getattr(lsp_client.config, 'extraction_timeout', 30.0)
                    signal.alarm(int(extraction_timeout))
                    
                    try:
                        argument_definitions = self._extract_argument_definitions(
                            func, repo_path, arg_extractor, lang_name
                        )
                        
                        # Perform focal method enrichment if enabled
                        focal_method_analysis = None
                        if focal_enricher:
                            try:
                                focal_method_analysis = focal_enricher.enrich_focal_method(func)
                                logger.debug(f"Enriched {func_name} with {focal_method_analysis['summary']['total_tokens']} tokens")
                            except Exception as e:
                                logger.warning(f"Could not enrich focal method for {func_name}: {e}")
                    finally:
                        signal.alarm(0)  # Cancel the alarm
                    
                    # Track function processing time
                    func_elapsed = time.time() - func_start_time
                    function_times.append(func_elapsed)
                    
                    # Log timing for slow functions (>10s)
                    if func_elapsed > 10:
                        logger.warning(f"⏱ Function {func_name} took {func_elapsed:.1f}s")
                    
                    # Check for LSP performance degradation and restart if needed
                    functions_since_restart += 1
                    recent_count = min(10, len(function_times))
                    should_restart = False
                    
                    # Rust-specific aggressive restart strategy (every 50 functions)
                    if lang_name == 'rust':
                        # Trigger 1: Every 50 functions (allow server time to index)
                        if functions_since_restart >= 50 and lsp_restarts < MAX_RESTARTS:
                            should_restart = True
                            logger.info(f"LSP restart triggered: {functions_since_restart} functions processed")
                        
                        # Trigger 2: Any function taking > 120s (emergency restart)
                        elif func_elapsed > 120 and lsp_restarts < MAX_RESTARTS:
                            should_restart = True
                            logger.info(f"LSP restart triggered: function took {func_elapsed:.1f}s (>120s threshold)")
                    else:
                        # Original strategy for other languages (Go, Julia, PHP, Ruby)
                        # Trigger 1: Every 50 functions (proactive restart)
                        if functions_since_restart >= 50 and lsp_restarts < MAX_RESTARTS:
                            should_restart = True
                            logger.info(f"LSP restart triggered: {functions_since_restart} functions processed")
                        
                        # Trigger 2: Performance degradation (high avg time and elapsed time)
                        elif recent_count >= 10:
                            avg_recent_time = sum(function_times[-recent_count:]) / recent_count
                            elapsed_total = time.time() - repo_start_time
                            
                            # Restart if avg time > 30s and more than 10 minutes elapsed
                            if (avg_recent_time > 30 and elapsed_total > 600) and lsp_restarts < MAX_RESTARTS:
                                should_restart = True
                                logger.info(
                                    f"LSP restart triggered: avg {avg_recent_time:.1f}s/func, "
                                    f"{elapsed_total/60:.1f}min elapsed"
                                )
                        
                    if should_restart:
                        logger.warning(f"⚠ Restarting LSP server (restart #{lsp_restarts + 1}/{MAX_RESTARTS})...")
                        try:
                            lsp_client.close()
                            time.sleep(2)
                            lsp_client = lsp_client_class(str(repo_path))
                            lsp_client.start()
                            arg_extractor = arg_extractor_class(lsp_client=lsp_client)
                            
                            # Update focal_enricher's LSP client reference to prevent broken pipe errors
                            if focal_enricher:
                                focal_enricher.lsp_client = lsp_client
                                # Update retrievers with new LSP client
                                if hasattr(focal_enricher, 'definition_retriever'):
                                    focal_enricher.definition_retriever.lsp_client = lsp_client
                                    if hasattr(focal_enricher.definition_retriever, 'opened_documents'):
                                        focal_enricher.definition_retriever.opened_documents.clear()
                                if hasattr(focal_enricher, 'reference_retriever'):
                                    focal_enricher.reference_retriever.lsp_client = lsp_client
                                    if hasattr(focal_enricher.reference_retriever, 'opened_documents'):
                                        focal_enricher.reference_retriever.opened_documents.clear()
                                logger.debug("✓ Updated focal_enricher and retrievers with new LSP client")
                            
                            lsp_restarts += 1
                            functions_since_restart = 0
                            function_times.clear()  # Reset timing tracking
                            repo_start_time = time.time()
                            logger.info("✓ LSP server restarted successfully")
                        except Exception as restart_err:
                            logger.error(f"Failed to restart LSP: {restart_err}")
                            # Reset counter even on failure to prevent continuous restart attempts
                            functions_since_restart = 0
                            # Continue with existing client
                    
                    # Mark function as successfully processed
                    out_func = deepcopy(func)
                    out_func.setdefault("function_component", {})
                    out_func["function_component"]["argument_definitions_lsp"] = argument_definitions
                    
                    # Add focal method analysis if available
                    if focal_method_analysis:
                        out_func["function_component"]["focal_method_analysis"] = focal_method_analysis
                    
                    out_func.setdefault("lsp_extraction", {})
                    out_func["lsp_extraction"].update({
                        "run_id": self._run_id,
                        "language": lang_name,
                        "repository": repo_path.name,
                        "status": "ok",
                        "focal_method_enriched": focal_method_analysis is not None,
                    })
                    self._append_jsonl(output_file, out_func)
                    processed_count += 1
                except TimeoutError as e:
                    logger.warning(f"Timeout processing function {func_name}: {e}")
                    self._append_jsonl(output_file, self._mark_as_error(
                        func, lang_name, repo_path.name, f"Timeout: {e}"
                    ))
                except Exception as e:
                    logger.error(f"Error processing function {func_name}: {e}")
                    self._append_jsonl(output_file, self._mark_as_error(
                        func, lang_name, repo_path.name, str(e)
                    ))
                    
        except Exception as e:
            logger.error(f"LSP server error for {repo_path.name}: {e}")
            # Add remaining functions as errors
            # We skip already processed ones in the loop if we were to continue, 
            # but here we just mark the rest of THIS repo as errors.
            for func in functions[processed_count:]:
                self._append_jsonl(output_file, self._mark_as_error(
                    func, lang_name, repo_path.name, f"LSP error: {e}"
                ))
        finally:
            if lsp_client:
                try:
                    lsp_client.close()
                except Exception as e:
                    logger.warning(f"Error closing LSP client: {e}")
        
        return []

    def _append_jsonl(self, file_path: Path, data: Dict):
        """Append a single record to the JSONL file."""
        if not file_path:
            return
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(data) + '\n')
            f.flush()

    def _deduplicate_file(self, file_path: Path):
        """Deduplicate JSONL file by task_id and sort."""
        if not file_path.exists():
            return
            
        from experiments.evaluation.common.task_ids import normalize_task_id, task_id_sort_key
        
        records = self._load_jsonl(file_path)
        results_by_id = {}

        for record in records:
            task_id = record.get('task_id')
            if task_id is not None:
                norm_id = normalize_task_id(task_id)
                record['task_id'] = norm_id
                results_by_id[norm_id] = record
            else:
                # Use (file_path, function_name) as fallback key
                key = (record['file_path'], record['function_name'])
                results_by_id[key] = record
                
        # Sort by task_id if possible
        def sort_key(r):
            tid = r.get('task_id')
            if tid is not None:
                return task_id_sort_key(tid)
            return (r['file_path'], r['function_name'])
            
        all_results = sorted(results_by_id.values(), key=sort_key)
        
        temp_file = file_path.with_suffix('.tmp')
        try:
            self._save_jsonl(temp_file, all_results)
            temp_file.replace(file_path)
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            logger.error(f"Failed to deduplicate {file_path}: {e}")
    
    def _extract_argument_definitions(
        self,
        func: Dict[str, Any],
        repo_path: Path,
        arg_extractor,
        lang_name: str,
    ) -> List[Dict[str, Any]]:
        """Extract argument definitions for a single function."""
        signature = func['function_component']['signature']
        file_path = func['file_path']
        
        # Extract the relative portion of repo_path (e.g., "burn-main/crates/burn-core" or "Rust-master")
        repo_path_parts = str(repo_path).split('/')
        # Find where the language folder ends (e.g., "rust/", "go/")
        lang_idx = None
        for i, part in enumerate(repo_path_parts):
            if part in ['rust', 'go', 'julia', 'ruby', 'php']:
                lang_idx = i
                break
        
        if lang_idx is not None and lang_idx + 1 < len(repo_path_parts):
            # Get everything after the language folder
            repo_relative_path = '/'.join(repo_path_parts[lang_idx + 1:])
            # If file_path starts with this, strip it
            if file_path.startswith(repo_relative_path + '/'):
                relative_path = file_path[len(repo_relative_path) + 1:]
                full_file_path = repo_path / relative_path
            else:
                # Fallback: just remove first component
                full_file_path = repo_path / file_path.split('/', 1)[1]
        else:
            # Fallback: just remove first component (repository name)
            full_file_path = repo_path / file_path.split('/', 1)[1]
        
        if not full_file_path.exists():
            logger.warning(f"File not found: {full_file_path}")
            return []
        
        # Use the LSP-based argument extractor
        try:
            definitions = arg_extractor.get_argument_definitions(
                str(full_file_path),
                signature
            )
            
            # Handle different return formats
            # Go extractor returns a list directly
            # Rust/Ruby/PHP/Julia extractors return a dict
            if isinstance(definitions, list):
                # Go format: already a list of argument definitions
                argument_definitions = []
                for arg in definitions:
                    type_defs = []
                    for def_info in arg.get('definitions', []):
                        type_defs.append({
                            'type_name': arg['type'],
                            'definition': def_info.get('type_definition', ''),
                            'location': def_info.get('definition_location', {})
                        })
                    
                    argument_definitions.append({
                        'name': arg['name'],
                        'type': arg['type'],
                        'definitions': type_defs
                    })
                return argument_definitions
            else:
                # Rust/Ruby/PHP/Julia format: dict of argument name -> info
                argument_definitions = []
                for arg_name, arg_info in definitions.items():
                    type_defs = []
                    for type_name, type_def in arg_info.get('definitions', {}).items():
                        type_defs.append({
                            'type_name': type_name,
                            'definition': type_def.get('type_definition', ''),
                            'location': type_def.get('definition_location', {})
                        })
                    
                    argument_definitions.append({
                        'name': arg_name,
                        'type': arg_info['type'],
                        'definitions': type_defs
                    })
                return argument_definitions
        except Exception as e:
            logger.debug(f"Could not extract definitions for {func.get('function_name', '?')}: {e}")
            return []
    
    def _mark_as_error(self, func: Dict, lang_name: str, repo_name: str, error_msg: str) -> Dict:
        """Mark a function as having an error during extraction."""
        out_func = deepcopy(func)
        out_func.setdefault("function_component", {})
        out_func["function_component"]["argument_definitions_lsp"] = []
        out_func.setdefault("lsp_extraction", {})
        out_func["lsp_extraction"].update({
            "run_id": self._run_id,
            "language": lang_name,
            "repository": repo_name,
            "status": "error",
            "error": error_msg,
        })
        return out_func
    
    def _load_jsonl(self, path: Path) -> List[Dict]:
        """Load JSONL file."""
        functions = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                functions.append(json.loads(line))
        return functions
    
    def _save_jsonl(self, path: Path, data: List[Dict]):
        """Save to JSONL file."""
        with open(path, 'w', encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item) + '\n')
    
    
    def _group_by_repo(self, functions: List[Dict]) -> Dict[str, List[Dict]]:
        """Group functions by repository name (or crate for Rust multi-crate projects)."""
        repo_functions = defaultdict(list)
        for func in functions:
            group_key = self._extract_repo_from_path(func['file_path'])
            repo_functions[group_key].append(func)
        return dict(repo_functions)
    
    def _extract_repo_from_path(self, file_path: str) -> str:
        """
        Extract repository name from file path.
        For Rust workspaces: 'burn-main/crates/burn-core/...' -> 'burn-main' (use workspace root)
        For others: 'Go-master/...' -> 'Go-master'
        
        This ensures all crates in a Rust workspace share the same LSP server instance,
        which is necessary for rust-analyzer to resolve cross-crate dependencies.
        """
        parts = file_path.split('/')
        
        # For all projects, just return the repository name (first component)
        # The RustLSPClient will automatically detect and use workspace roots
        return parts[0]


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="LSP-based Argument Extractor")
    parser.add_argument("--language", type=str, help="Language to process (go, rust, ruby, php, julia)")
    parser.add_argument("--input-file", type=str, help="Path to input JSONL file")
    parser.add_argument("--repo-dir", type=str, help="Base directory for repositories")
    parser.add_argument("--limit", type=int, help="Maximum number of functions to process per language")
    
    args = parser.parse_args()
    
    logger.info("\n" + "="*60)
    logger.info("LSP-based Argument Extractor")
    logger.info("="*60 + "\n")
    
    from xrepotest.paths import get_project_root
    workspace_root = get_project_root()
    extractor = ArgumentExtractor(workspace_root, limit=args.limit)
    
    # Determine languages to process
    if args.language:
        languages = [args.language.lower()]
    else:
        languages = ['go', 'rust', 'ruby', 'php', 'julia']
    
    # Process selected languages
    for lang in languages:
        logger.info(f"\n{'='*60}")
        logger.info(f"Starting {lang.upper()} extraction")
        logger.info("="*60 + "\n")
        
        try:
            # Convert paths to Path objects if provided
            input_file = Path(args.input_file) if args.input_file else None
            repo_base = Path(args.repo_dir) if args.repo_dir else None
            
            extractor.extract_for_language(lang, input_file=input_file, repo_base=repo_base)
        except Exception as e:
            logger.error(f"Failed to process {lang}: {e}")
            import traceback
            traceback.print_exc()
    
    logger.info("\n" + "="*60)
    logger.info("Extraction complete!")
    logger.info("="*60)


if __name__ == '__main__':
    main()
