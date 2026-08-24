"""
BM25-based retrieval for RAG.
Uses BM25Okapi algorithm for keyword-based relevance ranking.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any
from rank_bm25 import BM25Okapi
from tqdm import tqdm

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from xrepotest.rag.utils.file_tools import FileTools
from xrepotest.paths import get_repo_data_dir


class BM25Retriever:
    """BM25-based code retrieval for RAG context."""
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """
        Initialize BM25 retriever.
        
        Args:
            k1: BM25 parameter controlling term frequency saturation
            b: BM25 parameter controlling document length normalization
        """
        self.k1 = k1
        self.b = b
    
    def retrieve_contexts(
        self,
        query: str,
        contexts: List[Dict[str, Any]],
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retrieve top-K most relevant contexts using BM25.
        
        Args:
            query: Query text (e.g., function signature)
            contexts: List of context dictionaries with 'context' field
            top_k: Number of top contexts to return
        
        Returns:
            List of top-K contexts with BM25 scores added
        """
        if not contexts:
            return []
        
        # Extract text and tokenize
        corpus_texts = [ctx.get('context', '') for ctx in contexts]
        tokenized_corpus = [text.split() for text in corpus_texts]
        tokenized_query = query.split()
        
        # Compute BM25 scores
        bm25 = BM25Okapi(tokenized_corpus, k1=self.k1, b=self.b)
        scores = bm25.get_scores(tokenized_query)
        
        # Add scores to contexts
        for i, ctx in enumerate(contexts):
            ctx['bm25_score'] = float(scores[i])
        
        # Sort by score and return top-K
        sorted_contexts = sorted(contexts, key=lambda x: x['bm25_score'], reverse=True)
        return sorted_contexts[:top_k]


def retrieve_from_windows(
    query: str,
    windows_path: str,
    current_file_path: str,
    input_fpath_tuple: tuple,
    import_file_tuples: List[tuple] = None,
    imported_context: bool = True,
    top_k: int = 10
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant code windows using BM25.
    
    Args:
        query: Query text for retrieval
        windows_path: Path to repo windows JSONL file
        current_file_path: Path to current file windows JSONL file
        input_fpath_tuple: Tuple of current file path
        import_file_tuples: List of tuples for imported files
        imported_context: If True, only retrieve from imported files
        top_k: Number of top windows to return
    
    Returns:
        List of top-K retrieved windows with scores
    """
    if import_file_tuples is None:
        import_file_tuples = []
    
    # Load windows
    updated_samples = []
    
    # Load repo windows
    if os.path.exists(windows_path):
        with open(windows_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                data = json.loads(line)
                metadata = data.get("metadata", [])
                
                # Filter based on imports
                if imported_context and import_file_tuples:
                    if len(metadata) == 1:
                        if (metadata[0].get("fpath_tuple") != input_fpath_tuple and 
                            metadata[0].get("fpath_tuple") in import_file_tuples):
                            updated_samples.append(data)
                    elif len(metadata) > 1:
                        new_metadata = [
                            meta for meta in metadata
                            if (meta.get("fpath_tuple") != input_fpath_tuple and 
                                meta.get("fpath_tuple") in import_file_tuples)
                        ]
                        if new_metadata:
                            data["metadata"] = new_metadata
                            updated_samples.append(data)
                else:
                    # Include all non-current file
                    if len(metadata) == 1:
                        if metadata[0].get("fpath_tuple") != input_fpath_tuple:
                            updated_samples.append(data)
                    elif len(metadata) > 1:
                        new_metadata = [
                            meta for meta in metadata
                            if meta.get("fpath_tuple") != input_fpath_tuple
                        ]
                        if new_metadata:
                            data["metadata"] = new_metadata
                            updated_samples.append(data)
    
    # Load current file windows
    if os.path.exists(current_file_path):
        with open(current_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                data = json.loads(line)
                data["metadata"] = [{"fpath_tuple": input_fpath_tuple}]
                updated_samples.append(data)
    
    # Retrieve using BM25
    if updated_samples and query:
        retriever = BM25Retriever()
        top_results = retriever.retrieve_contexts(query, updated_samples, top_k)
        return top_results
    
    return []


def retrieve_for_sample(
    sample: Dict[str, Any],
    repo_base_dir: str = None,
    windows_dir: str = "data/cache/windows",
    top_k: int = 10
) -> Dict[str, Any]:
    """
    Retrieve relevant contexts for an xrepotest function sample.
    
    Args:
        sample: xrepotest JSONL sample with function metadata
        repo_base_dir: Base directory containing repositories (defaults to
                       project-root repo_data/)
        windows_dir: Directory containing window files
        top_k: Number of contexts to retrieve
    
    Returns:
        Sample with added 'retrieved_contexts_bm25' field
    """
    if repo_base_dir is None:
        repo_base_dir = str(get_repo_data_dir())
    # Extract metadata
    file_path = sample.get('file_path', '')
    function_name = sample.get('function_name', '')
    focal_code = sample.get('focal_code', '')
    
    # Use focal code as query
    query = focal_code or function_name
    
    # Determine repo from file path
    path_parts = file_path.split('/')
    if len(path_parts) < 2:
        print(f"Warning: Invalid file path format: {file_path}")
        sample['retrieved_contexts_bm25'] = []
        return sample
    
    repo_name = path_parts[0]
    relative_path = '/'.join(path_parts[1:])
    
    # Construct window paths
    repo_windows_path = os.path.join(
        windows_dir, 
        f"repo_{repo_name}_ws20_ss2.jsonl"
    )
    
    current_file_windows_path = os.path.join(
        windows_dir,
        f"current_{relative_path.replace('/', '_')}_ws20_ss2.jsonl"
    )
    
    # Build file tuple
    input_fpath_tuple = tuple(file_path.split('/'))
    
    # Retrieve contexts
    try:
        retrieved = retrieve_from_windows(
            query=query,
            windows_path=repo_windows_path,
            current_file_path=current_file_windows_path,
            input_fpath_tuple=input_fpath_tuple,
            import_file_tuples=[],  # No import info in xrepotest data
            imported_context=False,  # Include all contexts
            top_k=top_k
        )
        
        sample['retrieved_contexts_bm25'] = retrieved
        
    except Exception as e:
        print(f"Error retrieving for {function_name}: {e}")
        sample['retrieved_contexts_bm25'] = []
    
    return sample


def process_file_bm25(
    input_path: str,
    output_path: str,
    repo_base_dir: str = None,
    windows_dir: str = "data/cache/windows",
    top_k: int = 10
):
    """
    Process an xrepotest JSONL file and add BM25 retrieved contexts.
    
    Args:
        input_path: Path to input xrepotest JSONL file
        output_path: Path to save output with retrievals
        repo_base_dir: Base directory for repositories (defaults to
                       project-root repo_data/)
        windows_dir: Directory with window files
        top_k: Number of contexts to retrieve per sample
    """
    if repo_base_dir is None:
        repo_base_dir = str(get_repo_data_dir())
    print(f"\nProcessing {input_path} with BM25 retrieval...")
    
    # Load samples
    samples = FileTools.load_jsonl(input_path)
    
    # Process each sample
    processed_samples = []
    for sample in tqdm(samples, desc="BM25 retrieval"):
        processed = retrieve_for_sample(
            sample,
            repo_base_dir=repo_base_dir,
            windows_dir=windows_dir,
            top_k=top_k
        )
        processed_samples.append(processed)
    
    # Save results
    FileTools.save_jsonl(processed_samples, output_path)
    print(f"Saved to {output_path}")
    
    return processed_samples


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="BM25 retrieval for xrepotest data")
    parser.add_argument("--input", required=True, help="Input xrepotest JSONL file")
    parser.add_argument("--output", required=True, help="Output JSONL file")
    parser.add_argument("--repo-base", default=None, help="Repository base directory (default: project-root repo_data/)")
    parser.add_argument("--windows-dir", default="data/cache/windows", help="Windows directory")
    parser.add_argument("--top-k", type=int, default=10, help="Number of contexts to retrieve")
    
    args = parser.parse_args()
    
    process_file_bm25(
        input_path=args.input,
        output_path=args.output,
        repo_base_dir=args.repo_base,
        windows_dir=args.windows_dir,
        top_k=args.top_k
    )
