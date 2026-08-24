"""
UniXcoder-based semantic retrieval for RAG.
Uses transformer embeddings for semantic similarity ranking.
"""

import json
import os
import sys
import pickle
from pathlib import Path
from typing import Dict, List, Any, Callable
import torch
import numpy as np
from transformers import RobertaTokenizer, RobertaModel
from sklearn.metrics.pairwise import cosine_similarity
from tqdm import tqdm

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from xrepotest.rag.utils.file_tools import FileTools
from xrepotest.paths import get_repo_data_dir


def has_line_overlap(start1: int, end1: int, start2: int, end2: int) -> bool:
    """
    Check if two line ranges overlap.
    
    Args:
        start1, end1: First range
        start2, end2: Second range
    
    Returns:
        True if ranges overlap
    """
    return not (end1 < start2 or end2 < start1)


class UniXcoderEmbedder:
    """Modified to cache embeddings for reuse with disk persistence."""
    
    def __init__(self, model_name: str = "microsoft/unixcoder-base", cache_dir: str = "data/cache/embeddings"):
        """
        Initialize UniXcoder embedder.
        
        Args:
            model_name: HuggingFace model name
            cache_dir: Directory to save/load embedding cache files
        """
        self.model_name = model_name
        self.cache = {}
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Using device: {self.device}")
        
        # Load model and tokenizer
        self.tokenizer = RobertaTokenizer.from_pretrained(model_name)
        self.model = RobertaModel.from_pretrained(model_name)
        self.model.to(self.device)
        self.model.eval()
    
    def get_embedding(self, text: str, max_length: int = 512) -> np.ndarray:
        """
        Get embedding for a single text.
        
        Args:
            text: Input text
            max_length: Maximum sequence length
        
        Returns:
            Numpy array of shape (1, hidden_size)
        """
        if text in self.cache:
            return self.cache[text]
        
        # Tokenize
        inputs = self.tokenizer(
            text,
            add_special_tokens=True,
            max_length=max_length,
            padding='max_length',
            truncation=True,
            return_tensors='pt'
        )
        
        input_ids = inputs['input_ids'].to(self.device)
        attention_mask = inputs['attention_mask'].to(self.device)
        
        # Get embeddings with mean pooling
        with torch.no_grad():
            outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
            embeddings = outputs.last_hidden_state
            
            # Apply attention mask and mean pool
            mask_expanded = attention_mask.unsqueeze(-1).expand(embeddings.size()).float()
            embeddings = embeddings * mask_expanded
            embeddings = torch.sum(embeddings, dim=1) / torch.clamp(
                mask_expanded.sum(1), min=1e-9
            )
        
        embedding = embeddings.cpu().numpy()
        self.cache[text] = embedding
        return embedding
    
    def get_batch_embeddings(
        self,
        texts: List[str],
        batch_size: int = 1024,
        max_length: int = 512
    ) -> np.ndarray:
        """
        Get embeddings for multiple texts in batches.
        
        Args:
            texts: List of input texts
            batch_size: Batch size for processing
            max_length: Maximum sequence length
        
        Returns:
            Numpy array of shape (len(texts), hidden_size)
        """
        # Separate cached and uncached texts
        uncached_texts = [text for text in texts if text not in self.cache]
        cached_count = len(texts) - len(uncached_texts)
        
        if uncached_texts:
            print(f"Computing embeddings for {len(uncached_texts)} new contexts ({cached_count} cached)")
            for i in tqdm(range(0, len(uncached_texts), batch_size), desc="Computing embeddings"):
                batch_texts = uncached_texts[i:i+batch_size]
                
                # Batch tokenization
                inputs = self.tokenizer(
                    batch_texts,
                    add_special_tokens=True,
                    max_length=max_length,
                    padding='max_length',
                    truncation=True,
                    return_tensors='pt'
                )
                
                input_ids = inputs['input_ids'].to(self.device)
                attention_mask = inputs['attention_mask'].to(self.device)
                
                # Get embeddings with mean pooling
                with torch.no_grad():
                    outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
                    embeddings = outputs.last_hidden_state
                    
                    # Apply attention mask and mean pool
                    mask_expanded = attention_mask.unsqueeze(-1).expand(embeddings.size()).float()
                    embeddings = embeddings * mask_expanded
                    sum_embeddings = torch.sum(embeddings, dim=1)
                    sum_mask = torch.clamp(mask_expanded.sum(1), min=1e-9)
                    batch_embeddings = (sum_embeddings / sum_mask).cpu().numpy()
                
                # Cache results
                for text, emb in zip(batch_texts, batch_embeddings):
                    self.cache[text] = emb.reshape(1, -1)
        elif cached_count > 0:
            print(f"Using {cached_count} cached embeddings")
        
        # Return embeddings in original order
        return np.vstack([self.cache[text] for text in texts])


class UniXcoderRetriever:
    """UniXcoder-based semantic code retrieval."""
    
    def __init__(self, model_name: str = "microsoft/unixcoder-base", cache_dir: str = "data/cache/embeddings"):
        """
        Initialize UniXcoder retriever.
        
        Args:
            model_name: HuggingFace model name
            cache_dir: Directory to save/load embedding cache files
        """
        self.embedder = UniXcoderEmbedder(model_name, cache_dir)
        self.repo_windows_cache = {}  # Cache loaded repo windows by path
    
    def preload_repo_windows(self, windows_path: str) -> List[Dict[str, Any]]:
        """
        Load and cache ALL repo windows with pre-computed embeddings.
        Saves/loads embeddings to/from disk for reuse across runs.
        
        Args:
            windows_path: Path to repo windows file
        
        Returns:
            All repo windows (unfiltered)
        """
        if windows_path in self.repo_windows_cache:
            return self.repo_windows_cache[windows_path]
        
        # Generate cache file path for embeddings
        windows_basename = os.path.basename(windows_path).replace('.jsonl', '')
        embeddings_cache_path = os.path.join(self.embedder.cache_dir, f"{windows_basename}_embeddings.pkl")
        
        all_windows = []
        if os.path.exists(windows_path):
            with open(windows_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    all_windows.append(json.loads(line))
        
        # Pre-compute embeddings for all repo windows
        if all_windows:
            corpus_texts = [ctx.get('context', '') for ctx in all_windows]
            
            # Try to load embeddings from disk
            if os.path.exists(embeddings_cache_path):
                try:
                    print(f"Loading cached embeddings from {os.path.basename(embeddings_cache_path)}...")
                    with open(embeddings_cache_path, 'rb') as f:
                        saved_cache = pickle.load(f)
                    # Merge saved embeddings into in-memory cache
                    self.embedder.cache.update(saved_cache)
                    print(f"Loaded {len(saved_cache)} cached embeddings")
                except Exception as e:
                    print(f"Warning: Could not load cached embeddings: {e}")
            
            # Compute any missing embeddings
            print(f"Pre-computing embeddings for {len(all_windows)} repo windows from {os.path.basename(windows_path)}...")
            _ = self.embedder.get_batch_embeddings(corpus_texts)
            
            # Save embeddings to disk for reuse
            try:
                # Only save embeddings for texts in this repo
                repo_embeddings = {text: self.embedder.cache[text] for text in corpus_texts if text in self.embedder.cache}
                with open(embeddings_cache_path, 'wb') as f:
                    pickle.dump(repo_embeddings, f)
                print(f"Saved {len(repo_embeddings)} embeddings to {os.path.basename(embeddings_cache_path)}")
            except Exception as e:
                print(f"Warning: Could not save embeddings cache: {e}")
        
        self.repo_windows_cache[windows_path] = all_windows
        return all_windows
    
    def retrieve_contexts(
        self,
        query: str,
        contexts: List[Dict[str, Any]],
        top_k: int = 10,
        focal_file_path: tuple = None,
        focal_start_line: int = None,
        focal_end_line: int = None,
        retrieve_multiplier: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Retrieve top-K most relevant contexts using semantic similarity.
        Filters out contexts from same file and overlapping line ranges.
        
        Args:
            query: Query text
            contexts: List of context dictionaries with 'context' field
            top_k: Number of top contexts to return after filtering
            focal_file_path: File path tuple of the focal function
            focal_start_line: Start line of focal function
            focal_end_line: End line of focal function
            retrieve_multiplier: Retrieve top_k * multiplier before filtering
        
        Returns:
            List of top-K contexts with similarity scores added
        """
        if not contexts:
            return []
        
        # Get embeddings
        corpus_texts = [ctx.get('context', '') for ctx in contexts]
        context_embeddings = self.embedder.get_batch_embeddings(corpus_texts)
        query_embedding = self.embedder.get_embedding(query)
        
        # Compute similarities
        similarities = cosine_similarity(query_embedding, context_embeddings)[0]
        
        # Add scores to contexts
        for i, ctx in enumerate(contexts):
            ctx['unixcoder_score'] = float(similarities[i])
        
        # Sort by score
        sorted_contexts = sorted(
            contexts, 
            key=lambda x: x['unixcoder_score'], 
            reverse=True
        )
        
        # Retrieve more than top_k initially
        initial_k = min(top_k * retrieve_multiplier, len(sorted_contexts))
        candidates = sorted_contexts[:initial_k]
        
        # Filter out contexts from same file and overlapping lines
        filtered = []
        for ctx in candidates:
            metadata = ctx.get('metadata', [])
            if not metadata:
                filtered.append(ctx)
                continue
            
            # Check if context is from the same file
            should_include = True
            for meta in metadata:
                ctx_fpath = meta.get('fpath_tuple')
                # Convert to tuple if it's a list
                if isinstance(ctx_fpath, list):
                    ctx_fpath = tuple(ctx_fpath)
                ctx_start = meta.get('start_line_no', -1)
                ctx_end = meta.get('end_line_no', -1)
                
                # Skip if from same file AND overlaps with focal function
                if focal_file_path and ctx_fpath == focal_file_path:
                    if focal_start_line is not None and focal_end_line is not None:
                        if has_line_overlap(focal_start_line, focal_end_line, ctx_start, ctx_end):
                            should_include = False
                            break
            
            if should_include:
                filtered.append(ctx)
            
            # Stop once we have enough
            if len(filtered) >= top_k:
                break
        
        return filtered[:top_k]


def retrieve_from_windows(
    query: str,
    windows_path: str,
    input_fpath_tuple: tuple,
    retriever: 'UniXcoderRetriever',
    focal_start_line: int = None,
    focal_end_line: int = None,
    import_file_tuples: List[tuple] = None,
    imported_context: bool = True,
    top_k: int = 10,
    window_size: int = 20,
    slice_size: int = 2
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant code windows using UniXcoder.
    Filters out windows from same file that overlap with focal function lines.
    
    Args:
        query: Query text for retrieval
        windows_path: Path to repo windows JSONL file
        input_fpath_tuple: Tuple of current file path
        retriever: Shared UniXcoderRetriever instance
        focal_start_line: Start line of focal function
        focal_end_line: End line of focal function
        import_file_tuples: List of tuples for imported files
        imported_context: If True, only retrieve from imported files
        top_k: Number of top windows to return
    
    Returns:
        List of top-K retrieved windows with scores
    """
    if import_file_tuples is None:
        import_file_tuples = []
    
    # Load repo windows from cache (embeddings pre-computed)
    all_repo_windows = retriever.preload_repo_windows(windows_path)
    
    # Filter cached windows based on current file
    updated_samples = []
    for data in all_repo_windows:
        data = data.copy()  # Don't modify cached data
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
            # Include all windows (filtering by overlap happens in retrieve_contexts)
            updated_samples.append(data)
    
    # Retrieve using UniXcoder with filtering
    if updated_samples and query:
        top_results = retriever.retrieve_contexts(
            query, 
            updated_samples, 
            top_k,
            focal_file_path=input_fpath_tuple,
            focal_start_line=focal_start_line,
            focal_end_line=focal_end_line
        )
        return top_results
    
    return []


def retrieve_for_sample(
    sample: Dict[str, Any],
    retriever: UniXcoderRetriever,
    repo_base_dir: str = None,
    windows_dir: str = "data/cache/windows",
    top_k: int = 10,
    window_size: int = 20,
    slice_size: int = 2
) -> Dict[str, Any]:
    """
    Retrieve relevant contexts for an xrepotest function sample.
    
    Args:
        sample: xrepotest JSONL sample with function metadata
        retriever: Shared UniXcoderRetriever instance
        repo_base_dir: Base directory containing repositories (defaults to
                       project-root repo_data/)
        windows_dir: Directory containing window files
        top_k: Number of contexts to retrieve
    
    Returns:
        Sample with added 'retrieved_contexts_unixcoder' field
    """
    if repo_base_dir is None:
        repo_base_dir = str(get_repo_data_dir())
    # Extract metadata
    file_path = sample.get('file_path', '')
    function_name = sample.get('function_name', '')
    focal_code = sample.get('focal_code', '')
    
    # Extract focal function line numbers
    function_component = sample.get('function_component', {})
    focal_start_line = function_component.get('start_line')
    focal_end_line = function_component.get('end_line')
    
    # Use focal code as query
    query = focal_code or function_name
    
    # Determine repo from file path
    path_parts = file_path.split('/')
    if len(path_parts) < 2:
        print(f"Warning: Invalid file path format: {file_path}")
        sample['retrieved_contexts_unixcoder'] = []
        return sample
    
    repo_name = path_parts[0]

    # Construct repo window path
    repo_windows_path = os.path.join(
        windows_dir, 
        f"repo_{repo_name}_ws{window_size}_ss{slice_size}.jsonl"
    )
    
    # Build file tuple
    input_fpath_tuple = tuple(file_path.split('/'))
    
    # Retrieve contexts
    try:
        retrieved = retrieve_from_windows(
            query=query,
            windows_path=repo_windows_path,
            input_fpath_tuple=input_fpath_tuple,
            retriever=retriever,
            focal_start_line=focal_start_line,
            focal_end_line=focal_end_line,
            import_file_tuples=[],  # No import info in xrepotest data
            imported_context=False,  # Include all contexts
            top_k=top_k,
            window_size=window_size,
            slice_size=slice_size
        )
        
        sample['retrieved_contexts_unixcoder'] = retrieved
        
    except Exception as e:
        print(f"Error retrieving for {function_name}: {e}")
        sample['retrieved_contexts_unixcoder'] = []
    
    return sample


def process_file_unixcoder(
    input_path: str,
    output_path: str,
    repo_base_dir: str = None,
    windows_dir: str = "data/cache/windows",
    top_k: int = 10,
    window_size: int = 20,
    slice_size: int = 2,
    cache_manager=None,
    normalize_task_id_fn: Callable[[Dict[str, Any]], Dict[str, Any]] | None = None,
):
    """
    Process an xrepotest JSONL file and add UniXcoder retrieved contexts.
    
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
    print(f"\nProcessing {input_path} with UniXcoder retrieval...")
    
    # Load samples
    samples = FileTools.load_jsonl(input_path)
    if normalize_task_id_fn is not None:
        samples = [normalize_task_id_fn(sample) for sample in samples]

    # Create shared retriever instance (reuses embeddings across all samples)
    print("Initializing UniXcoder retriever...")
    retriever = UniXcoderRetriever()

    # Pre-load all unique repo windows and compute embeddings once
    print("Pre-loading and embedding repository windows...")
    unique_repos = set()
    existing_results = cache_manager.load_existing_results(output_path) if cache_manager is not None else {}
    if cache_manager is not None:
        samples_to_process = []
        for sample in samples:
            task_id = sample.get("task_id")
            existing_record = existing_results.get(task_id)
            # Only skip rows that already contain the UniXcoder stage output.
            if existing_record is not None and "retrieved_contexts_unixcoder" in existing_record:
                continue
            samples_to_process.append(sample)
    else:
        samples_to_process = samples

    if cache_manager is not None and not samples_to_process:
        print(f"All {len(samples)} samples already processed. Skipping.")
        cache_manager.deduplicate_file(output_path)
        return None

    repo_source_samples = samples_to_process if cache_manager is not None else samples
    for sample in repo_source_samples:
        file_path = sample.get('file_path', '')
        if file_path:
            repo_name = file_path.split('/') if '/' in file_path else []
            if repo_name:
                unique_repos.add(repo_name[0])

    for repo_name in unique_repos:
        repo_windows_path = os.path.join(windows_dir, f"repo_{repo_name}_ws{window_size}_ss{slice_size}.jsonl")
        if os.path.exists(repo_windows_path):
            # This will load and cache embeddings for the repo
            retriever.preload_repo_windows(repo_windows_path)

    print(f"Pre-loaded {len(unique_repos)} repositories")

    # Process each sample
    if cache_manager is not None:
        for sample in tqdm(samples_to_process, desc="Retrieving contexts"):
            processed = retrieve_for_sample(
                sample,
                retriever=retriever,
                repo_base_dir=repo_base_dir,
                windows_dir=windows_dir,
                top_k=top_k,
                window_size=window_size,
                slice_size=slice_size,
            )
            cache_manager.append_result(output_path, processed)
        cache_manager.deduplicate_file(output_path)
        print(f"Saved to {output_path}")
        return None

    processed_samples = []
    for sample in tqdm(samples, desc="Retrieving contexts"):
        processed = retrieve_for_sample(
            sample,
            retriever=retriever,
            repo_base_dir=repo_base_dir,
            windows_dir=windows_dir,
            top_k=top_k,
            window_size=window_size,
            slice_size=slice_size,
        )
        processed_samples.append(processed)

    FileTools.save_jsonl(processed_samples, output_path)
    print(f"Saved to {output_path}")
    return processed_samples


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="UniXcoder retrieval for xrepotest data")
    parser.add_argument("--input", required=True, help="Input xrepotest JSONL file")
    parser.add_argument("--output", required=True, help="Output JSONL file")
    parser.add_argument("--repo-base", default=None, help="Repository base directory (default: project-root repo_data/)")
    parser.add_argument("--windows-dir", default="data/cache/windows", help="Windows directory")
    parser.add_argument("--top-k", type=int, default=10, help="Number of contexts to retrieve")
    parser.add_argument("--window-size", type=int, default=20, help="Window size used in preprocessing")
    parser.add_argument("--slice-size", type=int, default=2, help="Slice size used in preprocessing")
    
    args = parser.parse_args()
    
    process_file_unixcoder(
        input_path=args.input,
        output_path=args.output,
        repo_base_dir=args.repo_base,
        windows_dir=args.windows_dir,
        top_k=args.top_k,
        window_size=args.window_size,
        slice_size=args.slice_size
    )
