"""
RAG Pipeline for Unit Test Generation.

This pipeline:
1. Processes repositories to create code windows
2. Runs both BM25 and UniXcoder retrieval
3. Adds retrieved contexts to xrepotest function data
4. Saves enriched data for unit test generation
"""

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any
from tqdm import tqdm

# Add to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from xrepotest.rag.utils.file_tools import FileTools
from xrepotest.rag.preprocessing.make_window import RepoWindowMaker
from xrepotest.rag.retrieval.bm25_retriever import BM25Retriever
from xrepotest.rag.retrieval.unixcoder_retriever import UniXcoderRetriever, process_file_unixcoder as unixcoder_process_file
from xrepotest.rag.cache_manager import RAGCacheManager
from xrepotest.paths import get_rag_enriched_dir, get_repo_data_dir
from experiments.evaluation.common.task_ids import normalize_task_id


class RAGPipeline:
    """
    End-to-end RAG pipeline for processing xrepotest data.
    """

    @staticmethod
    def _derive_stable_task_id(sample: Dict[str, Any]) -> str:
        file_path = sample.get("file_path", "")
        function_name = sample.get("function_name", "")
        function_component = sample.get("function_component", {}) or {}
        start_line = function_component.get("start_line")
        end_line = function_component.get("end_line")

        payload = json.dumps(
            [file_path, function_name, start_line, end_line],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
        return f"rag:{digest}"

    def _ensure_task_id(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        sample_task_id = sample.get("task_id")
        if sample_task_id is None or (isinstance(sample_task_id, str) and not sample_task_id.strip()):
            sample_task_id = self._derive_stable_task_id(sample)
        sample["task_id"] = normalize_task_id(sample_task_id)
        return sample

    def _normalize_samples_task_ids(self, samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [self._ensure_task_id(sample) for sample in samples]

    def __init__(
        self,
        repo_base_dir: str = None,
        windows_dir: str = "data/cache/windows",
        output_dir: str | None = None,
        window_size: int = 20,
        slice_size: int = 2,
        top_k: int = 10
    ):
        """
        Initialize RAG pipeline.
        
        Args:
            repo_base_dir: Base directory containing repositories (defaults to
                           project-root repo_data/)
            windows_dir: Directory to store/load code windows
            output_dir: Directory for output files
            window_size: Number of lines per window
            slice_size: Window overlap size
            top_k: Number of contexts to retrieve
        """
        if repo_base_dir is None:
            repo_base_dir = str(get_repo_data_dir())
        if output_dir is None:
            output_dir = str(get_rag_enriched_dir())
        self.repo_base_dir = repo_base_dir
        self.windows_dir = windows_dir
        self.output_dir = output_dir
        self.window_size = window_size
        self.slice_size = slice_size
        self.top_k = top_k
        self.cache_manager = RAGCacheManager()
        
        # Create directories
        os.makedirs(windows_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)
    
    def create_repo_windows(self, language: str, repo_name: str):
        """
        Create code windows for a repository.
        
        Args:
            language: Programming language (go, julia, php, ruby, rust)
            repo_name: Repository name
        """
        print(f"\n{'='*60}")
        print(f"Creating windows for {repo_name} ({language})")
        print(f"{'='*60}")
        
        repo_path = os.path.join(self.repo_base_dir, language, repo_name)
        
        if not os.path.exists(repo_path):
            print(f"Warning: Repository not found: {repo_path}")
            return
        
        # Create repo window maker
        maker = RepoWindowMaker(
            repo_path=repo_path,
            repo_name=repo_name,
            window_size=self.window_size,
            slice_size=self.slice_size
        )
        
        # Build and save windows
        output_path = os.path.join(
            self.windows_dir,
            f"repo_{repo_name}_ws{self.window_size}_ss{self.slice_size}.jsonl"
        )
        
        maker.build_windows(output_path)
    
    def create_all_repo_windows(self, languages: List[str] = None):
        """
        Create windows for all repositories.
        
        Args:
            languages: List of languages to process (default: all)
        """
        if languages is None:
            languages = ['go', 'julia', 'php', 'ruby', 'rust']
        
        print(f"\n{'#'*60}")
        print("CREATING REPOSITORY WINDOWS")
        print(f"{'#'*60}")
        
        for language in languages:
            lang_dir = os.path.join(self.repo_base_dir, language)
            
            if not os.path.exists(lang_dir):
                print(f"Warning: Language directory not found: {lang_dir}")
                continue
            
            # Get all repos for this language
            repos = [d for d in os.listdir(lang_dir) 
                    if os.path.isdir(os.path.join(lang_dir, d))]
            
            print(f"\nProcessing {len(repos)} {language} repositories...")
            
            for repo in repos:
                try:
                    self.create_repo_windows(language, repo)
                except Exception as e:
                    print(f"Error processing {repo}: {e}")
                    continue
    
    def retrieve_for_sample(
        self,
        sample: Dict[str, Any],
        use_bm25: bool = True,
        use_unixcoder: bool = True
    ) -> Dict[str, Any]:
        """
        Retrieve relevant contexts for a single xrepotest sample.
        
        Args:
            sample: xrepotest function sample
            use_bm25: Whether to use BM25 retrieval
            use_unixcoder: Whether to use UniXcoder retrieval
        
        Returns:
            Sample with retrieved contexts added
        """
        # Extract metadata
        file_path = sample.get('file_path', '')
        focal_code = sample.get('focal_code', '')
        function_name = sample.get('function_name', '')
        
        # Extract focal function line numbers
        function_component = sample.get('function_component', {})
        focal_start_line = function_component.get('start_line')
        focal_end_line = function_component.get('end_line')
        
        # Use focal code as query
        query = focal_code or function_name
        
        # Parse file path
        path_parts = file_path.split('/')
        if len(path_parts) < 2:
            print(f"Warning: Invalid file path: {file_path}")
            return sample
        
        repo_name = path_parts[0]

        # Construct window paths
        repo_windows_path = os.path.join(
            self.windows_dir,
            f"repo_{repo_name}_ws{self.window_size}_ss{self.slice_size}.jsonl"
        )
        
        # Build file tuple
        input_fpath_tuple = tuple(file_path.split('/'))
        
        # BM25 retrieval
        if use_bm25:
            try:
                if not os.path.exists(repo_windows_path):
                    print(f"Warning: Repo windows not found for {repo_name}")
                    sample['retrieved_contexts_bm25'] = []
                else:
                    # For xrepotest data, we don't have current file windows
                    # So we retrieve only from repo windows
                    retrieved_bm25 = self._retrieve_from_repo_only(
                        query, repo_windows_path, input_fpath_tuple,
                        focal_start_line=focal_start_line,
                        focal_end_line=focal_end_line,
                        retriever_type='bm25'
                    )
                    sample['retrieved_contexts_bm25'] = retrieved_bm25
            except Exception as e:
                print(f"BM25 error for {function_name}: {e}")
                sample['retrieved_contexts_bm25'] = []
        
        # UniXcoder retrieval
        if use_unixcoder:
            try:
                if not os.path.exists(repo_windows_path):
                    print(f"Warning: Repo windows not found for {repo_name}")
                    sample['retrieved_contexts_unixcoder'] = []
                else:
                    retrieved_unixcoder = self._retrieve_from_repo_only(
                        query, repo_windows_path, input_fpath_tuple,
                        focal_start_line=focal_start_line,
                        focal_end_line=focal_end_line,
                        retriever_type='unixcoder'
                    )
                    sample['retrieved_contexts_unixcoder'] = retrieved_unixcoder
            except Exception as e:
                print(f"UniXcoder error for {function_name}: {e}")
                sample['retrieved_contexts_unixcoder'] = []
        
        return sample
    
    def _retrieve_from_repo_only(
        self,
        query: str,
        repo_windows_path: str,
        input_fpath_tuple: tuple,
        focal_start_line: int = None,
        focal_end_line: int = None,
        retriever_type: str = 'bm25'
    ) -> List[Dict[str, Any]]:
        """
        Retrieve from repo windows only (no current file windows).
        Filters out windows that overlap with focal function line range.
        
        Args:
            query: Query text
            repo_windows_path: Path to repo windows file
            input_fpath_tuple: Current file path tuple
            focal_start_line: Start line of focal function
            focal_end_line: End line of focal function
            retriever_type: 'bm25' or 'unixcoder'
        
        Returns:
            List of retrieved contexts
        """
        import json

        def _has_line_overlap(start1: int, end1: int, start2: int, end2: int) -> bool:
            return not (end1 < start2 or end2 < start1)

        def _normalize_fpath_tuple(value):
            if isinstance(value, tuple):
                return value
            if isinstance(value, list):
                return tuple(value)
            return value
        
        # Load repo windows
        contexts = []
        with open(repo_windows_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                data = json.loads(line)
                # Filter windows: exclude only overlapping windows from same file
                metadata = data.get("metadata", [])
                filtered_meta = []
                
                for m in metadata:
                    ctx_fpath = _normalize_fpath_tuple(m.get("fpath_tuple"))
                    # Keep window if it's from a different file
                    if ctx_fpath != input_fpath_tuple:
                        filtered_meta.append(m)
                    # Or if it's from same file but doesn't overlap with focal function
                    elif focal_start_line is not None and focal_end_line is not None:
                        ctx_start = m.get('start_line_no', -1)
                        ctx_end = m.get('end_line_no', -1)
                        if not _has_line_overlap(focal_start_line, focal_end_line, ctx_start, ctx_end):
                            filtered_meta.append(m)
                
                if filtered_meta:
                    data["metadata"] = filtered_meta
                    contexts.append(data)
        
        # Retrieve using selected method
        if retriever_type == 'bm25':
            retriever = BM25Retriever()
        elif retriever_type == 'unixcoder':
            retriever = UniXcoderRetriever()
        else:
            raise ValueError(f"Unknown retriever type: {retriever_type}")
        
        top_results = retriever.retrieve_contexts(query, contexts, self.top_k)
        return top_results
    
    def process_file(
        self,
        input_path: str,
        output_path: str,
        use_bm25: bool = True,
        use_unixcoder: bool = True
    ):
        """
        Process an xrepotest JSONL file with retrieval.
        
        Args:
            input_path: Input xrepotest JSONL file
            output_path: Output path for enriched data
            use_bm25: Whether to use BM25 retrieval
            use_unixcoder: Whether to use UniXcoder retrieval
        """
        print(f"\n{'='*60}")
        print(f"Processing: {input_path}")
        print(f"{'='*60}")
        
        # Load samples
        samples = FileTools.load_jsonl(input_path)
        samples = self._normalize_samples_task_ids(samples)
        print(f"Loaded {len(samples)} samples")

        # Run BM25 retrieval if requested
        if use_bm25:
            bm25_output_path = self._get_stage_output_path(output_path, "bm25")
            existing_bm25_results = self.cache_manager.load_existing_results(bm25_output_path)
            bm25_samples_to_process = self.cache_manager.filter_samples(samples, existing_bm25_results)
            if not bm25_samples_to_process:
                print(f"All {len(samples)} samples already processed for BM25. Skipping.")
                self.cache_manager.deduplicate_file(bm25_output_path)
            for sample in tqdm(bm25_samples_to_process, desc="BM25 retrieval"):
                processed = self.retrieve_for_sample(sample, use_bm25=True, use_unixcoder=False)
                self.cache_manager.append_result(bm25_output_path, processed)
            self.cache_manager.deduplicate_file(bm25_output_path)
            print(f"\nSaved BM25 enriched data to: {bm25_output_path}")

        # Run UniXcoder retrieval if requested
        if use_unixcoder:
            unixcoder_output_path = self._get_stage_output_path(output_path, "unixcoder")

            # Use optimized UniXcoder process with caching
            processed_samples = unixcoder_process_file(
                input_path=input_path,
                output_path=unixcoder_output_path,
                repo_base_dir=self.repo_base_dir,
                windows_dir=self.windows_dir,
                top_k=self.top_k,
                window_size=self.window_size,
                slice_size=self.slice_size,
                cache_manager=self.cache_manager,
                normalize_task_id_fn=self._ensure_task_id,
            )
            if processed_samples is not None:
                self.cache_manager.deduplicate_file(unixcoder_output_path)
            print(f"\nSaved UniXcoder enriched data to: {unixcoder_output_path}")
    
    def _get_config_suffix(self) -> str:
        """Generate config suffix for output filenames."""
        return f"_ws{self.window_size}_ss{self.slice_size}_k{self.top_k}"

    @staticmethod
    def _get_stage_output_path(output_path: str, stage: str) -> str:
        stem, ext = os.path.splitext(output_path)
        return f"{stem}_{stage}{ext}"
    
    def process_all_files(
        self,
        input_dir: str = "xrepotest_input",
        use_bm25: bool = True,
        use_unixcoder: bool = True
    ):
        """
        Process all xrepotest JSONL files.
        
        Args:
            input_dir: Directory containing xrepotest files
            use_bm25: Whether to use BM25 retrieval
            use_unixcoder: Whether to use UniXcoder retrieval
        """
        print(f"\n{'#'*60}")
        print("PROCESSING ALL XREPOTEST FILES")
        print(f"Config: window_size={self.window_size}, slice_size={self.slice_size}, top_k={self.top_k}")
        print(f"{'#'*60}")
        
        # Find all JSONL files
        jsonl_files = [
            f for f in os.listdir(input_dir)
            if f.endswith('.jsonl')
        ]
        
        print(f"Found {len(jsonl_files)} xrepotest files")
        
        for filename in jsonl_files:
            input_path = os.path.join(input_dir, filename)
            
            # Create output filename with config suffix
            config_suffix = self._get_config_suffix()
            output_filename = filename.replace('.jsonl', f'{config_suffix}_enriched.jsonl')
            output_path = os.path.join(self.output_dir, output_filename)
            
            try:
                self.process_file(
                    input_path, output_path, use_bm25, use_unixcoder
                )
            except Exception as e:
                print(f"Error processing {filename}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"\n{'#'*60}")
        print("PIPELINE COMPLETE")
        print(f"Results saved to: {self.output_dir}")
        print(f"{'#'*60}")


def main():
    """Main entry point for RAG pipeline."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="RAG Pipeline for Unit Test Generation"
    )
    parser.add_argument(
        "--mode",
        choices=["windows", "retrieve", "full"],
        default="full",
        help="Pipeline mode: windows (create windows), retrieve (run retrieval), full (both)"
    )
    parser.add_argument(
        "--input-dir",
        default="xrepotest_input",
        help="Directory containing xrepotest JSONL files"
    )
    parser.add_argument(
        "--repo-base",
        default=None,
        help="Base directory for repositories (default: project-root repo_data/)"
    )
    parser.add_argument(
        "--windows-dir",
        default="data/cache/windows",
        help="Directory for code windows"
    )
    parser.add_argument(
        "--output-dir",
        default=str(get_rag_enriched_dir()),
        help="Output directory for enriched data (default: project-root data/enriched/rag)"
    )
    parser.add_argument(
        "--languages",
        nargs='+',
        default=['go', 'julia', 'php', 'ruby', 'rust'],
        help="Languages to process"
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=20,
        help="Window size in lines"
    )
    parser.add_argument(
        "--slice-size",
        type=int,
        default=2,
        help="Slice size for window overlap"
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of contexts to retrieve"
    )
    parser.add_argument(
        "--no-bm25",
        action="store_true",
        help="Disable BM25 retrieval"
    )
    parser.add_argument(
        "--no-unixcoder",
        action="store_true",
        help="Disable UniXcoder retrieval"
    )
    
    args = parser.parse_args()
    
    # Initialize pipeline
    pipeline = RAGPipeline(
        repo_base_dir=args.repo_base,
        windows_dir=args.windows_dir,
        output_dir=args.output_dir,
        window_size=args.window_size,
        slice_size=args.slice_size,
        top_k=args.top_k
    )
    
    # Run pipeline
    if args.mode in ["windows", "full"]:
        pipeline.create_all_repo_windows(args.languages)
    
    if args.mode in ["retrieve", "full"]:
        pipeline.process_all_files(
            input_dir=args.input_dir,
            use_bm25=not args.no_bm25,
            use_unixcoder=not args.no_unixcoder
        )


if __name__ == "__main__":
    main()
