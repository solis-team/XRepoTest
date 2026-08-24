"""
File I/O and repository navigation utilities.
Replaces the missing 'utils' module from the original code.
"""

import os
import json
from typing import Dict, List, Tuple, Any


class FileTools:
    """Tools for file operations and code reading."""
    
    @staticmethod
    def read_code(file_path: str, encoding: str = 'utf-8') -> str:
        """
        Read code from a file.
        
        Args:
            file_path: Path to the file
            encoding: File encoding (default: utf-8)
            
        Returns:
            File content as string
        """
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            # Fallback to latin-1 if utf-8 fails
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
    
    @staticmethod
    def load_jsonl(file_path: str) -> List[Dict[str, Any]]:
        """
        Load JSONL file (one JSON object per line).
        
        Args:
            file_path: Path to JSONL file
            
        Returns:
            List of dictionaries
        """
        data = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    data.append(json.loads(line))
        return data
    
    @staticmethod
    def save_jsonl(data: List[Dict[str, Any]], file_path: str):
        """
        Save data to JSONL file.
        
        Args:
            data: List of dictionaries to save
            file_path: Output file path
        """
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
    
    @staticmethod
    def iterate_repository(repo_name: str, base_dir: str, 
                          extensions: Tuple[str, ...] = None) -> Dict[Tuple[str, ...], str]:
        """
        Iterate through all source files in a repository.
        
        Args:
            repo_name: Name of the repository
            base_dir: Base directory containing repositories
            extensions: Tuple of file extensions to include (e.g., ('.py', '.go'))
                       If None, includes common source code extensions
            
        Returns:
            Dictionary mapping file path tuples to file contents
            Example: {('repo', 'src', 'file.py'): 'file content'}
        """
        if extensions is None:
            # Default source code extensions
            extensions = (
                '.py', '.go', '.java', '.js', '.ts', '.cpp', '.c', '.h', 
                '.hpp', '.rs', '.rb', '.php', '.jl', '.scala', '.kt'
            )
        
        repo_path = os.path.join(base_dir, repo_name)
        if not os.path.exists(repo_path):
            raise FileNotFoundError(f"Repository not found: {repo_path}")
        
        files_dict = {}
        
        for root, dirs, files in os.walk(repo_path):
            # Skip common non-source directories
            dirs[:] = [d for d in dirs if d not in {
                '.git', '.svn', '__pycache__', 'node_modules', 
                '.pytest_cache', '.mypy_cache', 'venv', 'env'
            }]
            
            for file in files:
                if file.endswith(extensions):
                    full_path = os.path.join(root, file)
                    
                    # Create relative path tuple
                    rel_path = os.path.relpath(full_path, base_dir)
                    path_parts = tuple(rel_path.replace('\\', '/').split('/'))
                    
                    try:
                        content = FileTools.read_code(full_path)
                        files_dict[path_parts] = content
                    except Exception as e:
                        print(f"Warning: Could not read {full_path}: {e}")
                        continue
        
        return files_dict


class FilePathBuilder:
    """Build and manage file paths for the project."""
    
    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir
    
    def get_repo_path(self, repo_name: str, repo_base_dir: str) -> str:
        """Get full path to a repository."""
        return os.path.join(self.base_dir, repo_base_dir, repo_name)
    
    def get_cache_path(self, *path_parts: str) -> str:
        """Get path in cache directory."""
        return os.path.join(self.base_dir, "data", "cache", *path_parts)
    
    def get_temp_path(self, *path_parts: str) -> str:
        """Get path in temp directory."""
        return os.path.join(self.base_dir, "data", "temp", *path_parts)
    
    def get_results_path(self, *path_parts: str) -> str:
        """Get path in results directory."""
        return os.path.join(self.base_dir, "data", "results", *path_parts)
    
    def ensure_dir(self, file_path: str):
        """Ensure directory for file path exists."""
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)


# Backwards compatibility aliases
Tools = FileTools
