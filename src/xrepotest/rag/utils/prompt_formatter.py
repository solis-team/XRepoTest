"""
Prompt formatting utilities shared across retrieval methods.
Extracted from bm25.py and unixcoder.py to avoid code duplication.
"""

import json
from collections import defaultdict
from typing import List, Dict, Any, Tuple


def format_retrieval_prompt(
    top_chunks: List[Dict[str, Any]],
    input_fpath_tuple: Tuple[str, ...],
    target_function_prompt: str,
    sep: str = "/"
) -> str:
    """
    Format retrieved code chunks into a prompt for LLM.
    
    Args:
        top_chunks: List of top-K retrieved chunks with metadata
        input_fpath_tuple: Tuple representing the current file path
        target_function_prompt: The function signature/prompt to complete
        sep: Path separator (default: "/")
    
    Returns:
        Formatted prompt string ready for LLM
    """
    input_module = sep.join(input_fpath_tuple)
    
    # Group chunks by module
    modules_dict = defaultdict(list)
    for sample in top_chunks:
        for metadata in sample.get("metadata", []):
            module_name = sep.join(metadata.get("fpath_tuple", []))
            modules_dict[module_name].append(sample)
    
    prompt_elements = [
        "You are a programmer working with a repository. "
        "Here is all the context you may find useful to complete the function:"
    ]
    
    # Add chunks from other modules first
    same_module_chunks = []
    for module_name, samples in modules_dict.items():
        if module_name != input_module:
            prompt_elements.append(f"\n#FILE: {module_name}")
            for i, sample in enumerate(samples):
                prompt_elements.append(f"##CHUNK {i+1}")
                prompt_elements.append(sample['context'])
                prompt_elements.append("")
        else:
            same_module_chunks.extend(samples)
    
    # Add chunks from current module
    if same_module_chunks:
        prompt_elements.append(f"\n#CURRENT FILE: {input_module}")
        for i, sample in enumerate(same_module_chunks):
            prompt_elements.append(f"##CHUNK {i+1}")
            prompt_elements.append(sample['context'])
            prompt_elements.append("")
    
    # Add final instruction
    prompt_elements.append(
        "\nBased on the information above, please complete the function in the current file:"
    )
    prompt_elements.append(target_function_prompt)
    
    return "\n".join(prompt_elements)


def load_and_filter_chunks(
    windows_path: str,
    current_fpath: str,
    input_fpath_tuple: Tuple[str, ...],
    import_file_tuples: List[Tuple[str, ...]],
    imported_context: bool = True
) -> List[Dict[str, Any]]:
    """
    Load code chunks from window files and filter based on imports.
    
    Args:
        windows_path: Path to repository windows JSONL file
        current_fpath: Path to current file windows JSONL file
        input_fpath_tuple: Tuple representing current file path
        import_file_tuples: List of tuples representing imported files
        imported_context: If True, only include chunks from imported files
    
    Returns:
        List of filtered code chunks with metadata
    """
    updated_samples = []
    
    # Load repo context windows
    if imported_context:
        with open(windows_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                    
                data = json.loads(line)
                metadata = data.get("metadata", [])
                
                if len(metadata) == 1:
                    # Single metadata: check if from import file and not current file
                    if (metadata[0].get("fpath_tuple") != input_fpath_tuple and 
                        metadata[0].get("fpath_tuple") in import_file_tuples):
                        updated_samples.append(data)
                        
                elif len(metadata) > 1:
                    # Multiple metadata: filter to import files only
                    new_metadata = [
                        meta for meta in metadata
                        if (meta.get("fpath_tuple") != input_fpath_tuple and 
                            meta.get("fpath_tuple") in import_file_tuples)
                    ]
                    if new_metadata:
                        data["metadata"] = new_metadata
                        updated_samples.append(data)
    else:
        # Include all files except current file
        with open(windows_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                    
                data = json.loads(line)
                metadata = data.get("metadata", [])
                
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
    
    # Add current file windows
    with open(current_fpath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            data = json.loads(line)
            data["metadata"] = [{"fpath_tuple": input_fpath_tuple}]
            updated_samples.append(data)
    
    return updated_samples
