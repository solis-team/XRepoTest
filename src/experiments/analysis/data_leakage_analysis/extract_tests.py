#!/usr/bin/env python3
"""
Extract test code samples from repository for data leakage detection.
Extracts 10 test samples per language (Go, Rust, Ruby, PHP, Julia) with JSONL output format.
"""

import json
import random
from pathlib import Path
from typing import List, Dict, Optional
import logging

from tree_sitter import Language, Parser
import tree_sitter_go
import tree_sitter_rust
import tree_sitter_ruby
import tree_sitter_php
import tree_sitter_julia

from xrepotest.paths import get_repo_data_dir, get_data_dir

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TestExtractor:
    """Extract test functions from source code repositories"""
    
    # Test file patterns per language
    TEST_PATTERNS = {
        'go': {
            'file_suffixes': ['_test.go'],
            'function_prefix': ['Test', 'Benchmark'],
        },
        'rust': {
            'file_suffixes': ['.rs'],  # Tests can be inline or in tests/ dir
            'test_attr': '#[test]',
            'test_module': '#[cfg(test)]',
        },
        'ruby': {
            'file_suffixes': ['_spec.rb'],
            'test_dirs': ['spec/'],
        },
        'php': {
            'file_suffixes': ['Test.php'],
            'test_dirs': ['tests/', 'test/'],
        },
        'julia': {
            'file_suffixes': ['.jl'],
            'test_dirs': ['test/'],
        }
    }
    
    def __init__(self, repo_root: Path, samples_per_lang: int = 10):
        self.repo_root = repo_root
        self.samples_per_lang = samples_per_lang
        
        # Initialize tree-sitter parsers
        GO_LANGUAGE = Language(tree_sitter_go.language())
        RUST_LANGUAGE = Language(tree_sitter_rust.language())
        RUBY_LANGUAGE = Language(tree_sitter_ruby.language())
        PHP_LANGUAGE = Language(tree_sitter_php.language_php())
        JULIA_LANGUAGE = Language(tree_sitter_julia.language())
        
        self.parsers = {
            'go': Parser(GO_LANGUAGE),
            'rust': Parser(RUST_LANGUAGE),
            'ruby': Parser(RUBY_LANGUAGE),
            'php': Parser(PHP_LANGUAGE),
            'julia': Parser(JULIA_LANGUAGE),
        }
    
    def find_test_files(self, language: str) -> List[Path]:
        """Find all test files for a given language"""
        lang_dir = self.repo_root / language
        if not lang_dir.exists():
            logger.warning(f"Language directory not found: {lang_dir}")
            return []
        
        patterns = self.TEST_PATTERNS[language]
        test_files = []
        
        # Search for test files
        if language == 'go':
            test_files = list(lang_dir.rglob('*_test.go'))
        elif language == 'rust':
            # Find files in tests/ directories or with #[test] annotations
            for rs_file in lang_dir.rglob('*.rs'):
                if 'tests/' in str(rs_file) or 'test/' in str(rs_file):
                    test_files.append(rs_file)
                else:
                    # Check if file contains #[test] or #[cfg(test)]
                    try:
                        content = rs_file.read_text(encoding='utf-8', errors='ignore')
                        if '#[test]' in content or '#[cfg(test)]' in content:
                            test_files.append(rs_file)
                    except Exception:
                        pass
        elif language == 'ruby':
            test_files = list(lang_dir.rglob('*_spec.rb'))
        elif language == 'php':
            test_files = list(lang_dir.rglob('*Test.php'))
        elif language == 'julia':
            # Julia test files are in test/ directories
            for test_dir in lang_dir.rglob('test/'):
                test_files.extend(test_dir.glob('*.jl'))
        
        logger.info(f"Found {len(test_files)} test files for {language}")
        return test_files
    
    def extract_test_functions(self, file_path: Path, language: str) -> List[Dict]:
        """Extract test functions from a test file"""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return []
        
        if language == 'go':
            return self._extract_go_tests(file_path, content)
        elif language == 'rust':
            return self._extract_rust_tests(file_path, content)
        elif language == 'ruby':
            return self._extract_ruby_tests(file_path, content)
        elif language == 'php':
            return self._extract_php_tests(file_path, content)
        elif language == 'julia':
            return self._extract_julia_tests(file_path, content)
        
        return []
    
    def _extract_go_tests(self, file_path: Path, content: str) -> List[Dict]:
        """Extract Go test functions using tree-sitter"""
        parser = self.parsers['go']
        tree = parser.parse(bytes(content, 'utf8'))
        
        test_functions = []
        
        def visit_node(node):
            if node.type == 'function_declaration':
                name_node = node.child_by_field_name('name')
                if name_node:
                    func_name = content[name_node.start_byte:name_node.end_byte]
                    # Check if function name starts with Test or Benchmark
                    if func_name.startswith('Test') or func_name.startswith('Benchmark'):
                        test_code = content[node.start_byte:node.end_byte]
                        
                        test_functions.append({
                            'test_code': test_code,
                            'language': 'go'
                        })
            
            for child in node.children:
                visit_node(child)
        
        visit_node(tree.root_node)
        return test_functions
    
    def _extract_rust_tests(self, file_path: Path, content: str) -> List[Dict]:
        """Extract Rust test functions using tree-sitter"""
        parser = self.parsers['rust']
        tree = parser.parse(bytes(content, 'utf8'))
        
        test_functions = []
        
        def has_test_attribute(node):
            """Check if function has #[test] attribute"""
            # Look for preceding attribute_item nodes
            prev = node.prev_sibling
            while prev and prev.type in ['attribute_item', 'line_comment']:
                if prev.type == 'attribute_item':
                    attr_text = content[prev.start_byte:prev.end_byte]
                    if '#[test]' in attr_text:
                        return True
                prev = prev.prev_sibling
            return False
        
        def visit_node(node):
            if node.type == 'function_item':
                if has_test_attribute(node):
                    name_node = node.child_by_field_name('name')
                    if name_node:
                        func_name = content[name_node.start_byte:name_node.end_byte]
                        start_line = node.start_point[0]
                        end_line = node.end_point[0]
                        test_code = content[node.start_byte:node.end_byte]
                        
                        test_functions.append({
                            'test_code': test_code,
                            'language': 'rust'
                        })
            
            for child in node.children:
                visit_node(child)
        
        visit_node(tree.root_node)
        return test_functions
    
    def _extract_ruby_tests(self, file_path: Path, content: str) -> List[Dict]:
        """Extract Ruby test functions (RSpec) using tree-sitter"""
        parser = self.parsers['ruby']
        tree = parser.parse(bytes(content, 'utf8'))
        
        test_functions = []
        
        def visit_node(node):
            # Look for 'it' blocks in RSpec
            if node.type == 'call':
                method_node = node.child_by_field_name('method')
                if method_node:
                    method_name = content[method_node.start_byte:method_node.end_byte]
                    if method_name in ['it', 'specify', 'example']:
                        test_code = content[node.start_byte:node.end_byte]
                        
                        test_functions.append({
                            'test_code': test_code,
                            'language': 'ruby'
                        })
            
            for child in node.children:
                visit_node(child)
        
        visit_node(tree.root_node)
        return test_functions
    
    def _extract_php_tests(self, file_path: Path, content: str) -> List[Dict]:
        """Extract PHP test functions using tree-sitter"""
        parser = self.parsers['php']
        tree = parser.parse(bytes(content, 'utf8'))
        
        test_functions = []
        
        def visit_node(node):
            if node.type == 'method_declaration':
                name_node = node.child_by_field_name('name')
                if name_node:
                    method_name = content[name_node.start_byte:name_node.end_byte]
                    # Check if method name starts with 'test'
                    if method_name.startswith('test'):
                        test_code = content[node.start_byte:node.end_byte]
                        
                        test_functions.append({
                            'test_code': test_code,
                            'language': 'php'
                        })
            
            for child in node.children:
                visit_node(child)
        
        visit_node(tree.root_node)
        return test_functions
    
    def _extract_julia_tests(self, file_path: Path, content: str) -> List[Dict]:
        """Extract Julia test functions using tree-sitter"""
        parser = self.parsers['julia']
        tree = parser.parse(bytes(content, 'utf8'))
        
        test_functions = []
        
        def visit_node(node):
            # Look for @testset macrocall_expression (Julia tree-sitter node type)
            if node.type == 'macrocall_expression':
                # Check if it's a @testset or @test macro
                macro_id_node = None
                for child in node.children:
                    if child.type == 'macro_identifier':
                        macro_id_node = child
                        break
                
                if macro_id_node:
                    macro_text = content[macro_id_node.start_byte:macro_id_node.end_byte]
                    
                    # Extract @testset blocks (ignore individual @test)
                    if '@testset' in macro_text:
                        # Get testset name from string literal
                        test_name = f"testset_line_{node.start_point[0]}"
                        for child in node.children:
                            if child.type == 'macro_argument_list':
                                for arg in child.children:
                                    if arg.type == 'string_literal':
                                        # Extract content between quotes
                                        string_content = content[arg.start_byte:arg.end_byte]
                                        # Remove quotes and clean up
                                        desc = string_content.strip('"\'').replace('\n', ' ')[:40]
                                        test_name = f"testset_{desc.replace(' ', '_').replace('.', '_')}"
                                        break
                                break
                        
                        test_code = content[node.start_byte:node.end_byte]
                        
                        # Limit test code size
                        if len(test_code) > 5000:
                            test_code = test_code[:5000] + "\n# ... truncated ..."
                        
                        test_functions.append({
                            'test_code': test_code,
                            'language': 'julia'
                        })
            
            for child in node.children:
                visit_node(child)
        
        visit_node(tree.root_node)
        return test_functions
    
    def extract_for_language(self, language: str, output_dir: Path) -> int:
        """Extract test samples for a specific language"""
        logger.info(f"Extracting test functions for {language}...")
        
        test_files = self.find_test_files(language)
        if not test_files:
            logger.warning(f"No test files found for {language}")
            return 0
        
        # Extract test functions from all files
        all_tests = []
        for test_file in test_files:
            tests = self.extract_test_functions(test_file, language)
            all_tests.extend(tests)
        
        logger.info(f"Extracted {len(all_tests)} test functions for {language}")
        
        # Randomly sample N tests (if samples_per_lang is None or 0, extract all)
        if self.samples_per_lang and self.samples_per_lang > 0 and len(all_tests) > self.samples_per_lang:
            sampled_tests = random.sample(all_tests, self.samples_per_lang)
        else:
            sampled_tests = all_tests
        
        # Save to JSONL
        output_file = output_dir / f"{language}_tests.jsonl"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for test in sampled_tests:
                f.write(json.dumps(test, ensure_ascii=False) + '\n')
        
        logger.info(f"Saved {len(sampled_tests)} test samples to {output_file}")
        return len(sampled_tests)
    
    def extract_all(self, output_dir: Path):
        """Extract test samples for all languages"""
        total = 0
        for language in ['go', 'rust', 'ruby', 'php', 'julia']:
            count = self.extract_for_language(language, output_dir)
            total += count
        
        logger.info(f"Total test samples extracted: {total}")
        return total


def get_default_repo_root() -> Path:
    """Get the default repo root directory."""
    return get_repo_data_dir()

def get_default_test_samples_dir() -> Path:
    """Get the default test samples output directory."""
    return get_data_dir() / 'test_samples'


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Extract test code samples for data leakage detection')
    parser.add_argument('--repo-root', type=Path, default=get_default_repo_root(),
                        help='Root directory containing language repositories')
    parser.add_argument('--output-dir', type=Path, default=get_default_test_samples_dir(),
                        help='Output directory for test JSONL files')
    parser.add_argument('--language', type=str, choices=['go', 'rust', 'ruby', 'php', 'julia', 'all'],
                        default='all', help='Language to extract (default: all)')
    parser.add_argument('--samples', type=int, default=10,
                        help='Number of samples per language (default: 10)')
    
    args = parser.parse_args()
    
    extractor = TestExtractor(args.repo_root, samples_per_lang=args.samples)
    
    if args.language == 'all':
        extractor.extract_all(args.output_dir)
    else:
        extractor.extract_for_language(args.language, args.output_dir)


if __name__ == '__main__':
    main()
