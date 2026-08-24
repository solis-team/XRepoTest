#!/usr/bin/env python3
"""
Extract test code from TestGenEval dataset using GitHub API.

TestGenEval contains test patches from GitHub repositories. This script:
1. Loads the kjain14/testgeneval dataset from HuggingFace
2. Uses GitHub API to fetch test file content at specific commits
3. Parses test files with tree-sitter to extract individual test functions
4. Saves test code samples in JSONL format

Output format matches existing test samples: {"test_code": str, "language": str}
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict
import argparse
import logging

import requests
from datasets import load_dataset
from tqdm import tqdm

from tree_sitter import Language, Parser
import tree_sitter_python as tspython

from xrepotest.paths import get_data_dir

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Language mapping based on file extensions
EXTENSION_TO_LANGUAGE = {
    '.py': 'python',
    '.go': 'go',
    '.rs': 'rust',
    '.rb': 'ruby',
    '.php': 'php',
    '.jl': 'julia',
    '.java': 'java',
    '.js': 'javascript',
    '.ts': 'typescript',
    '.cpp': 'cpp',
    '.c': 'c',
    '.cs': 'csharp',
}


class GitHubAPIClient:
    """Simple GitHub API client with rate limiting and retry logic."""
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get('GITHUB_TOKEN')
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({'Authorization': f'token {self.token}'})
        self.rate_limit_remaining = 5000
        self.rate_limit_reset = 0
        self.logger = logging.getLogger(__name__)
    
    def get_file_content(self, repo: str, file_path: str, commit: str) -> Optional[str]:
        """
        Fetch file content from GitHub at a specific commit.
        
        Args:
            repo: Repository in format "owner/repo"
            file_path: Path to file in repository
            commit: Git commit SHA
            
        Returns:
            File content as string, or None if fetch fails
        """
        url = f"https://api.github.com/repos/{repo}/contents/{file_path}?ref={commit}"
        
        # Check rate limit
        if self.rate_limit_remaining < 10:
            wait_time = max(0, self.rate_limit_reset - time.time())
            if wait_time > 0:
                self.logger.info(f"Rate limit low ({self.rate_limit_remaining} remaining), waiting {wait_time:.0f}s...")
                time.sleep(wait_time + 1)
        
        try:
            response = self.session.get(url, timeout=30)
            
            # Update rate limit info
            self.rate_limit_remaining = int(response.headers.get('X-RateLimit-Remaining', 5000))
            self.rate_limit_reset = int(response.headers.get('X-RateLimit-Reset', time.time()))
            
            if response.status_code == 200:
                data = response.json()
                # Content is base64 encoded
                import base64
                content = base64.b64decode(data['content']).decode('utf-8', errors='ignore')
                return content
            elif response.status_code == 404:
                self.logger.warning(f"File not found: {repo}/{file_path} @ {commit[:8]}")
                return None
            elif response.status_code == 403:
                self.logger.warning(f"Rate limit exceeded or access forbidden")
                return None
            else:
                self.logger.warning(f"HTTP {response.status_code} for {repo}/{file_path}")
                return None
                
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Request error: {e}")
            return None
        except Exception as e:
            self.logger.warning(f"Unexpected error: {e}")
            return None



class TestGenEvalExtractor:
    """Extract test code from TestGenEval dataset."""
    
    def __init__(self, output_dir: Path, github_token: Optional[str] = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.github_client = GitHubAPIClient(token=github_token)
        
        # Initialize tree-sitter parser for Python
        try:
            PY_LANGUAGE = Language(tspython.language())
            self.parser = Parser(PY_LANGUAGE)
        except Exception as e:
            self.logger.warning(f"Failed to initialize Python parser: {e}")
            self.parser = None
    
    def _extract_python_test_functions(self, content: str) -> List[Dict]:
        """
        Extract individual test functions from Python test file.
        
        Args:
            content: Full Python file content
            
        Returns:
            List of test function dictionaries
        """
        if not self.parser:
            # Fallback: return entire file as one test
            return [{'test_code': content, 'language': 'python'}]
        
        tree = self.parser.parse(bytes(content, 'utf8'))
        test_functions = []
        
        def visit_node(node):
            """Recursively visit nodes to find test functions and test classes."""
            if node.type == 'function_definition':
                # Get function name
                name_node = node.child_by_field_name('name')
                if name_node:
                    func_name = content[name_node.start_byte:name_node.end_byte]
                    # Check if it's a test function (starts with 'test_')
                    if func_name.startswith('test_'):
                        test_code = content[node.start_byte:node.end_byte]
                        test_functions.append({
                            'test_code': test_code,
                            'language': 'python'
                        })
            
            elif node.type == 'class_definition':
                # Check if it's a test class (starts with 'Test' or contains 'Test')
                name_node = node.child_by_field_name('name')
                if name_node:
                    class_name = content[name_node.start_byte:name_node.end_byte]
                    if 'Test' in class_name or 'test' in class_name.lower():
                        # Extract all methods from test class
                        body_node = node.child_by_field_name('body')
                        if body_node:
                            for child in body_node.children:
                                if child.type == 'function_definition':
                                    method_name_node = child.child_by_field_name('name')
                                    if method_name_node:
                                        method_name = content[method_name_node.start_byte:method_name_node.end_byte]
                                        # Include test methods and setUp/tearDown
                                        if method_name.startswith('test_') or method_name in ['setUp', 'tearDown', 'setUpClass', 'tearDownClass']:
                                            test_code = content[child.start_byte:child.end_byte]
                                            test_functions.append({
                                                'test_code': test_code,
                                                'language': 'python'
                                            })
            
            # Continue visiting children for top-level nodes
            for child in node.children:
                visit_node(child)
        
        visit_node(tree.root_node)
        
        # If no test functions found, return empty list (skip this file)
        return test_functions
        
    def extract_tests(self, split: str = 'test', max_samples: int = 0) -> Dict[str, int]:
        """
        Extract test code from TestGenEval dataset.
        
        TestGenEval is a Python-only dataset, so all tests are Python.
        
        Args:
            split: Dataset split to process (test/train/validation)
            max_samples: Maximum samples to process (0 = all)
            
        Returns:
            Dictionary with counts per language
        """
        self.logger.info(f"Loading TestGenEval dataset (split: {split})...")
        self.logger.info(f"Note: TestGenEval is Python-only")
        ds = load_dataset("kjain14/testgeneval", trust_remote_code=True)
        
        if split not in ds:
            raise ValueError(f"Split '{split}' not found. Available: {list(ds.keys())}")
        
        dataset = ds[split]
        total_samples = len(dataset)
        self.logger.info(f"Loaded {total_samples} samples")
        
        if max_samples > 0:
            dataset = dataset.select(range(min(max_samples, total_samples)))
            self.logger.info(f"Processing first {len(dataset)} samples (limited by max_samples)")
        
        # TestGenEval is Python-only
        python_samples = []
        skipped_count = 0
        skipped_no_tests = 0
        
        self.logger.info(f"Extracting test code from GitHub...")
        for sample in tqdm(dataset, desc="Processing samples"):
            repo = sample['repo']
            test_file = sample['test_file']
            base_commit = sample['base_commit']
            
            # Fetch test file content from GitHub
            test_file_content = self.github_client.get_file_content(repo, test_file, base_commit)
            
            if test_file_content is None:
                skipped_count += 1
                continue
            
            # Parse and extract individual test functions
            test_functions = self._extract_python_test_functions(test_file_content)
            
            if not test_functions:
                skipped_no_tests += 1
                continue
            
            # Add all extracted test functions to samples
            python_samples.extend(test_functions)
        
        # Write output file (Python-only)
        stats = {}
        if python_samples:
            output_path = self.output_dir / "python_tests.jsonl"
            with open(output_path, 'w', encoding='utf-8') as f:
                for sample in python_samples:
                    f.write(json.dumps(sample) + '\n')
            stats['python'] = len(python_samples)
            self.logger.info(f"Saved {len(python_samples)} Python test functions to {output_path}")
        
        self.logger.info(f"Total test functions extracted: {len(python_samples)}")
        self.logger.info(f"Skipped (fetch failed): {skipped_count}")
        self.logger.info(f"Skipped (no test functions found): {skipped_no_tests}")
        self.logger.info(f"Files processed: {len(dataset) - skipped_count}")
        self.logger.info(f"Average functions per file: {len(python_samples) / max(1, len(dataset) - skipped_count - skipped_no_tests):.1f}")
        
        return stats


def get_default_output_dir() -> Path:
    """Get the default TestGenEval output directory."""
    return get_data_dir() / 'test_samples_testgeneval'


def main():
    logger = logging.getLogger(__name__)
    parser = argparse.ArgumentParser(
        description='Extract test code from TestGenEval dataset using GitHub API'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default=str(get_default_output_dir()),
        help=f'Output directory for JSONL files (default: {{data_dir}}/test_samples_testgeneval)'
    )
    parser.add_argument(
        '--split',
        type=str,
        default='test',
        choices=['test', 'train', 'validation'],
        help='Dataset split to process (default: test)'
    )
    parser.add_argument(
        '--max-samples',
        type=int,
        default=0,
        help='Maximum samples to process (0 = all, default: 0)'
    )
    parser.add_argument(
        '--github-token',
        type=str,
        default=None,
        help='GitHub API token (or set GITHUB_TOKEN env var)'
    )
    
    args = parser.parse_args()
    
    # Check for GitHub token
    github_token = args.github_token or os.environ.get('GITHUB_TOKEN')
    if not github_token:
        logger.warning("No GitHub token provided. Rate limits will be very restrictive (60 requests/hour).")
        logger.warning("Set GITHUB_TOKEN environment variable or use --github-token for higher limits (5000 requests/hour).")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            logger.info("Aborted. Get a token at: https://github.com/settings/tokens")
            return
    
    extractor = TestGenEvalExtractor(
        output_dir=Path(args.output_dir),
        github_token=github_token
    )
    
    extractor.extract_tests(
        split=args.split,
        max_samples=args.max_samples
    )


if __name__ == '__main__':
    main()
