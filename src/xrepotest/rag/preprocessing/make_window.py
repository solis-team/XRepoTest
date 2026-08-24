"""
Code windowing for unit test generation.
Creates sliding window contexts from repository code for RAG retrieval.

This module provides tools to:
1. Remove target functions from files to prevent leakage
2. Create overlapping code windows for context retrieval
3. Generate windows from entire repositories
"""

import os
import json
from collections import defaultdict
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from xrepotest.rag.utils import FileTools, FilePathBuilder


class CodeWindowMaker:
    """
    Create sliding windows from source code.
    Base class for different windowing strategies.
    """
    
    def __init__(self, window_size: int = 50, slice_size: int = 10):
        """
        Args:
            window_size: Number of lines per window
            slice_size: Step size for sliding window
        """
        self.window_size = window_size
        self.slice_size = slice_size
        self.slice_step = max(1, window_size // slice_size)
    
    def create_windows_from_code(self, code: str, metadata_base: dict) -> list:
        """
        Create overlapping windows from code.
        
        Args:
            code: Source code as string
            metadata_base: Base metadata to include in each window
        
        Returns:
            List of window dictionaries with context and metadata
        """
        code_windows = []
        code_lines = code.splitlines()
        delta_size = self.window_size // 2
        
        for line_no in range(0, len(code_lines), self.slice_step):
            start_line_no = max(0, line_no - delta_size)
            end_line_no = min(len(code_lines), line_no + self.window_size - delta_size)
            window_lines = code_lines[start_line_no:end_line_no]
            
            # Skip empty windows
            if not any(line.strip() for line in window_lines):
                continue
            
            window_text = '\n'.join(window_lines)
            
            # Create metadata for this window
            metadata = {
                **metadata_base,
                'line_no': line_no,
                'start_line_no': start_line_no,
                'end_line_no': end_line_no,
                'window_size': self.window_size,
                'slice_size': self.slice_size
            }
            
            code_windows.append({
                'context': window_text,
                'metadata': metadata
            })
        
        return code_windows
    
    def merge_windows_by_context(self, code_windows: list) -> list:
        """
        Merge windows with identical context.
        
        Args:
            code_windows: List of window dictionaries
        
        Returns:
            List of merged windows with multiple metadata entries
        """
        merged_windows = defaultdict(list)
        
        for window in code_windows:
            context = window['context']
            metadata = window['metadata']
            merged_windows[context].append(metadata)
        
        return [
            {'context': context, 'metadata': metadata_list}
            for context, metadata_list in merged_windows.items()
        ]


class UnitTestWindowMaker(CodeWindowMaker):
    """
    Create windows for unit test generation.
    - Removes target function from file
    - Creates windows from remaining code
    - Preserves context (imports, other functions)
    """
    
    def __init__(self, file_path: str, repo_name: str, start_line: int, 
                 end_line: int, window_size: int = 50, slice_size: int = 10):
        """
        Args:
            file_path: Relative path to file in repository
            repo_name: Repository name
            start_line: Start line of target function (0-indexed)
            end_line: End line of target function (0-indexed)
            window_size: Lines per window
            slice_size: Window overlap size
        """
        super().__init__(window_size, slice_size)
        
        self.file_path = file_path
        self.repo_name = repo_name
        self.start_line = start_line
        self.end_line = end_line
        
        # Read source code
        if os.path.exists(file_path):
            self.source_code = FileTools.read_code(file_path)
        else:
            raise FileNotFoundError(f"File not found: {file_path}")
    
    def remove_target_function(self) -> str:
        """Remove target function from source code using line numbers."""
        code_lines = self.source_code.splitlines()
        
        # Remove lines from start_line to end_line
        modified_lines = code_lines[:self.start_line] + code_lines[self.end_line:]
        
        print(f"Removed function from line {self.start_line} to {self.end_line}")
        print(f"Original: {len(code_lines)} lines -> Modified: {len(modified_lines)} lines")
        
        return '\n'.join(modified_lines)
    
    def build_windows(self, output_path: str = None) -> list:
        """
        Build windows from file with target function removed.
        
        Args:
            output_path: Optional path to save windows
        
        Returns:
            List of merged windows
        """
        # Remove target function
        modified_code = self.remove_target_function()
        
        # Create metadata base
        file_tuple = tuple(self.file_path.replace('\\', '/').split('/'))
        metadata_base = {
            'fpath_tuple': file_tuple,
            'repo': self.repo_name,
            'type': 'current_file'
        }
        
        # Create windows
        code_windows = self.create_windows_from_code(modified_code, metadata_base)
        merged_windows = self.merge_windows_by_context(code_windows)
        
        print(f'Built {len(merged_windows)} windows for {self.file_path} '
              f'(window_size={self.window_size}, slice_size={self.slice_size})')
        
        # Save if output path provided
        if output_path:
            FilePathBuilder().ensure_dir(output_path)
            with open(output_path, 'w', encoding='utf-8') as f:
                for window in merged_windows:
                    f.write(json.dumps(window) + '\n')
            print(f'Saved to: {output_path}')
        
        return merged_windows


class RepoWindowMaker(CodeWindowMaker):
    """
    Create windows from entire repository.
    Useful for retrieving context from other files.
    """
    
    def __init__(self, repo_path: str, repo_name: str, 
                 exclude_file: str = None,
                 window_size: int = 50, slice_size: int = 10):
        """
        Args:
            repo_path: Path to repository directory
            repo_name: Repository name
            exclude_file: Relative path to file to exclude
            window_size: Lines per window
            slice_size: Window overlap size
        """
        super().__init__(window_size, slice_size)
        
        self.repo_path = repo_path
        self.repo_name = repo_name
        self.exclude_file = exclude_file
        
        # Get all files in repo
        self.source_files = self._get_repo_files()
    
    def _get_repo_files(self) -> dict:
        """Get all source files in repository."""
        # Iterate through repository
        files_dict = FileTools.iterate_repository(
            self.repo_name, 
            os.path.dirname(self.repo_path)
        )
        
        # Exclude specific file if provided
        if self.exclude_file:
            exclude_tuple = tuple(self.exclude_file.replace('\\', '/').split('/'))
            files_dict = {
                k: v for k, v in files_dict.items() 
                if k != exclude_tuple
            }
            print(f"Excluded file: {self.exclude_file}")
        
        print(f"Processing {len(files_dict)} files from repository")
        return files_dict
    
    def build_windows(self, output_path: str = None) -> list:
        """
        Build windows from all files in repository.
        
        Args:
            output_path: Optional path to save windows
        
        Returns:
            List of merged windows from entire repo
        """
        all_windows = []
        
        for file_tuple, code in self.source_files.items():
            metadata_base = {
                'fpath_tuple': file_tuple,
                'repo': self.repo_name,
                'type': 'repo_context'
            }
            
            windows = self.create_windows_from_code(code, metadata_base)
            all_windows.extend(windows)
        
        # Merge windows with same context
        merged_windows = self.merge_windows_by_context(all_windows)
        
        print(f'Built {len(merged_windows)} windows from {len(self.source_files)} files '
              f'(window_size={self.window_size}, slice_size={self.slice_size})')
        
        # Save if output path provided
        if output_path:
            FilePathBuilder().ensure_dir(output_path)
            with open(output_path, 'w', encoding='utf-8') as f:
                for window in merged_windows:
                    f.write(json.dumps(window) + '\n')
            print(f'Saved to: {output_path}')
        
        return merged_windows


def process_function_for_rag(
    repo_path: str,
    repo_name: str,
    file_path: str,
    start_line: int,
    end_line: int,
    window_size: int = 20,
    slice_size: int = 2,
    output_dir: str = "data/cache/windows"
) -> dict:
    """
    Process a single function for RAG retrieval.
    Creates both current file windows and repo context windows.
    
    Args:
        repo_path: Path to repository directory
        repo_name: Repository name
        file_path: Relative path to file containing function
        start_line: Function start line (0-indexed)
        end_line: Function end line (0-indexed)
        window_size: Lines per window
        slice_size: Window overlap
        output_dir: Directory to save windows
    
    Returns:
        Dictionary with paths to window files
    """
    print(f"\n{'='*60}")
    print(f"Processing function in {file_path}")
    print(f"Lines {start_line} to {end_line}")
    print(f"{'='*60}\n")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Build current file windows (with function removed)
    print("Step 1: Creating current file windows (function removed)...")
    file_full_path = os.path.join(repo_path, file_path)
    
    current_maker = UnitTestWindowMaker(
        file_path=file_full_path,
        repo_name=repo_name,
        start_line=start_line,
        end_line=end_line,
        window_size=window_size,
        slice_size=slice_size
    )
    
    # Generate safe filename
    safe_filename = file_path.replace('/', '_').replace('\\', '_')
    current_output = os.path.join(
        output_dir, 
        f"current_{safe_filename}_ws{window_size}_ss{slice_size}.jsonl"
    )
    
    current_windows = current_maker.build_windows(current_output)
    
    # Build repo context windows (excluding current file)
    print("\nStep 2: Creating repo context windows (excluding current file)...")
    
    repo_maker = RepoWindowMaker(
        repo_path=repo_path,
        repo_name=repo_name,
        exclude_file=file_path,
        window_size=window_size,
        slice_size=slice_size
    )
    
    repo_output = os.path.join(
        output_dir,
        f"repo_{repo_name}_ws{window_size}_ss{slice_size}.jsonl"
    )
    
    repo_windows = repo_maker.build_windows(repo_output)
    
    print(f"\n{'='*60}")
    print("Summary:")
    print(f"  Current file windows: {len(current_windows)}")
    print(f"  Repo context windows: {len(repo_windows)}")
    print(f"  Total: {len(current_windows) + len(repo_windows)}")
    print(f"{'='*60}\n")
    
    return {
        'current_file_windows': current_output,
        'repo_windows': repo_output,
        'metadata': {
            'repo': repo_name,
            'file_path': file_path,
            'start_line': start_line,
            'end_line': end_line,
            'window_size': window_size,
            'slice_size': slice_size
        }
    }


if __name__ == "__main__":
    # Example usage
    import argparse
    
    parser = argparse.ArgumentParser(description="Create code windows for RAG")
    parser.add_argument("--repo-path", required=True, help="Path to repository")
    parser.add_argument("--repo-name", required=True, help="Repository name")
    parser.add_argument("--file-path", required=True, help="Relative path to file")
    parser.add_argument("--start-line", type=int, required=True, help="Function start line (0-indexed)")
    parser.add_argument("--end-line", type=int, required=True, help="Function end line (0-indexed)")
    parser.add_argument("--window-size", type=int, default=20, help="Window size")
    parser.add_argument("--slice-size", type=int, default=2, help="Slice size")
    parser.add_argument("--output-dir", default="data/cache/windows", help="Output directory")
    
    args = parser.parse_args()
    
    result = process_function_for_rag(
        repo_path=args.repo_path,
        repo_name=args.repo_name,
        file_path=args.file_path,
        start_line=args.start_line,
        end_line=args.end_line,
        window_size=args.window_size,
        slice_size=args.slice_size,
        output_dir=args.output_dir
    )
    
    print("\nWindow files created:")
    print(f"  Current file: {result['current_file_windows']}")
    print(f"  Repo context: {result['repo_windows']}")
