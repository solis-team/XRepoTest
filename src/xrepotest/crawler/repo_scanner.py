#!/usr/bin/env python3
"""
Repository Scanner Module
Scans repository directory structure and manages file filtering
"""

from pathlib import Path
from typing import List, Tuple

from xrepotest.crawler.default_config import load_crawler_config
from xrepotest.paths import get_repo_data_dir


class RepositoryScanner:
    """Scans repository directory structure."""
    
    def __init__(self, config_path: str = 'config.json'):
        self.config = load_crawler_config(config_path)
        self.file_extensions = {
            lang.lower(): exts
            for lang, exts in self.config['file_extensions'].items()
        }
        self.test_patterns = self.config['test_patterns']
    
    def scan_repo_directory(self, base_path: str = None) -> List[Tuple[str, str, str]]:
        """
        Scan repository directory and return list of (language, repo_path, repo_name).
        
        Returns:
            List of tuples: (language, full_repo_path, repo_name)
        """
        if base_path is None:
            base_path = str(get_repo_data_dir())
        repos = []
        base = Path(base_path)
        
        if not base.exists():
            print(f"Error: Base path {base_path} does not exist")
            return repos
        
        # Iterate through language directories
        for lang_dir in base.iterdir():
            if not lang_dir.is_dir():
                continue
            
            language = lang_dir.name.lower()
            
            # Iterate through repositories in each language directory
            for repo_dir in lang_dir.iterdir():
                if not repo_dir.is_dir():
                    continue
                
                repo_name = repo_dir.name
                repo_path = str(repo_dir)
                
                repos.append((language, repo_path, repo_name))
                print(f"Found: {language}/{repo_name}")
        
        return repos
    
    def is_test_file(self, file_path: str) -> bool:
        """Check if file is a test file based on patterns."""
        path_str = file_path.lower()
        
        # Check exclude paths
        for pattern in self.test_patterns['exclude_paths']:
            if pattern in path_str:
                return True
        
        # Check exclude file patterns
        for pattern in self.test_patterns['exclude_files']:
            if pattern.lower() in Path(file_path).name.lower():
                return True
        
        return False
    
    def get_source_files(self, repo_path: str, language: str) -> List[str]:
        """Get all source files for a given language in repository."""
        extensions = self.file_extensions.get(language.lower(), [])
        source_files = []
        
        repo = Path(repo_path)
        for ext in extensions:
            # Use glob pattern to ensure file ends with extension
            for file_path in repo.rglob(f'*{ext}'):
                # Double check file actually ends with the extension
                if str(file_path).endswith(ext) and not self.is_test_file(str(file_path)):
                    source_files.append(str(file_path))
        
        return source_files
