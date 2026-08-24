#!/usr/bin/env python3
"""
Refactored Multi-Language Repository Crawler
Modular structure with testing framework pre-check
"""

import json
from dataclasses import asdict
from typing import List, Dict, Optional
from collections import defaultdict
from pathlib import Path
import argparse

from xrepotest.crawler.repo_scanner import RepositoryScanner
from xrepotest.crawler.extractors.language_parser import LanguageParser
from xrepotest.crawler.extractors.function_extractor import FunctionExtractor
from xrepotest.paths import get_repo_data_dir, get_project_root


def resolve_config_path(config_path: str) -> str:
    """Resolve crawler config path from cwd/module/project root fallback."""
    candidate = Path(config_path)
    if candidate.is_file():
        return str(candidate)
    
    module_candidate = Path(__file__).resolve().parent / config_path
    if module_candidate.is_file():
        return str(module_candidate)
    
    project_candidate = get_project_root() / config_path
    if project_candidate.is_file():
        return str(project_candidate)
    
    return str(candidate)


class RepositoryCrawler:
    """Main crawler orchestrator."""
    
    def __init__(self, config_path: str = 'config.json', base_path: str = None):
        resolved_config_path = resolve_config_path(config_path)
        self.scanner = RepositoryScanner(resolved_config_path)
        self.lang_parser = LanguageParser()
        self.extractor = FunctionExtractor(self.lang_parser, resolved_config_path)
        self.base_path = base_path if base_path is not None else str(get_repo_data_dir())
        # Default output directory sits next to this module file, matching existing data layout.
        self.default_output_dir = Path(__file__).parent / 'extracted'
        self.stats = defaultdict(lambda: defaultdict(int))
    
    def crawl_repository(self, repo_path: str, language: str, repo_name: str) -> List[Dict]:
        """Crawl a single repository and extract all functions."""
        print(f"\n{'='*60}")
        print(f"Crawling: {repo_name} ({language})")
        print(f"{'='*60}")
        
        # Get source files
        source_files = self.scanner.get_source_files(repo_path, language)
        print(f"Found {len(source_files)} source files")
        
        all_functions = []
        
        for i, file_path in enumerate(source_files, 1):
            if i % 10 == 0:
                print(f"Processing file {i}/{len(source_files)}...")
            
            functions = self.extractor.parse_source_file(
                file_path, language, repo_name, repo_path
            )
            
            all_functions.extend(functions)
        
        # Update stats
        self.stats[language][repo_name] += len(all_functions)
        
        print(f"✓ Extracted {len(all_functions)} functions from {repo_name}")
        return [asdict(f) for f in all_functions]
    
    def crawl_all(self, output_dir: Optional[str] = None):
        """Crawl all repositories and save results."""
        out_dir = Path(output_dir) if output_dir else self.default_output_dir
        print("Starting repository scan...")
        repos = self.scanner.scan_repo_directory(self.base_path)
        print(f"\nFound {len(repos)} repositories to crawl\n")
        
        results_by_language = defaultdict(list)
        
        for language, repo_path, repo_name in repos:
            try:
                functions = self.crawl_repository(repo_path, language, repo_name)
                results_by_language[language].extend(functions)
            except Exception as e:
                print(f"✗ Error crawling {repo_name}: {e}")
        
        # Save results
        print(f"\n{'='*60}")
        print("Saving results...")
        
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Save each language to separate JSONL file
        total_saved = 0
        for language, functions in results_by_language.items():
            lang_file = out_dir / f'{language.lower()}_functions.jsonl'
            with open(lang_file, 'w', encoding='utf-8') as f:
                for func in functions:
                    f.write(json.dumps(func, ensure_ascii=False) + '\n')
            print(f"✓ Saved {len(functions)} {language} functions to {lang_file}")
            total_saved += len(functions)
        
        print(f"✓ Total: {total_saved} functions saved to {out_dir}/")
        
        # Print statistics
        self.print_statistics()
        
        # Save statistics next to the output files
        self.save_statistics(str(out_dir / 'crawler_statistics.json'))
    
    def print_statistics(self):
        """Print extraction statistics."""
        print(f"\n{'='*60}")
        print("EXTRACTION STATISTICS")
        print(f"{'='*60}")
        
        total_functions = 0
        lang_totals = defaultdict(int)
        
        for language, repos in self.stats.items():
            print(f"\n{language}:")
            for repo, count in repos.items():
                print(f"  {repo}: {count} functions")
                lang_totals[language] += count
                total_functions += count
        
        print(f"\n{'='*60}")
        print("TOTALS BY LANGUAGE:")
        for language, count in lang_totals.items():
            print(f"  {language}: {count} functions")
        
        print(f"\nTOTAL FUNCTIONS EXTRACTED: {total_functions}")
        
        print(f"\n{'='*60}\n")
    
    def save_statistics(self, stats_file: str):
        """Save statistics to JSON file."""
        stats_data = {
            'total_functions': sum(sum(repos.values()) for repos in self.stats.values()),
            'by_language': {
                lang: {
                    'total': sum(repos.values()),
                    'by_repo': dict(repos)
                }
                for lang, repos in self.stats.items()
            }
        }
        
        with open(stats_file, 'w') as f:
            json.dump(stats_data, f, indent=2)
        
        print(f"✓ Statistics saved to {stats_file}")


def main():
    """Main entry point."""
    supported_languages = "go, rust, julia, ruby, php"
    parser = argparse.ArgumentParser(description='Multi-Language Repository Crawler')
    parser.add_argument('--base-path', default=None, 
                       help='Base path to repository directory (default: project-root repo_data/)')
    parser.add_argument('--config', default='config.json',
                       help='Path to configuration file (default: config.json with module/project fallback)')
    parser.add_argument('--output', default='extracted_functions.jsonl',
                       help='Output file path (used for filtered crawls)')
    parser.add_argument('--output-dir', default=None,
                       help='Output directory for full crawl (default: <module-dir>/extracted/)')
    parser.add_argument('--language', 
                       help=f'Filter by specific language ({supported_languages})')
    parser.add_argument('--repo',
                       help='Filter by specific repository name')
    
    args = parser.parse_args()
    

    
    crawler = RepositoryCrawler(args.config, args.base_path)
    
    # If filtering by language or repo
    if args.language or args.repo:
        repos = crawler.scanner.scan_repo_directory(args.base_path)
        
        # Filter repositories
        filtered_repos = []
        for language, repo_path, repo_name in repos:
            if args.language and language.lower() != args.language.lower():
                continue
            if args.repo and repo_name != args.repo:
                continue
            filtered_repos.append((language, repo_path, repo_name))
        
        print(f"Filtered to {len(filtered_repos)} repositories")
        
        all_results = []
        for language, repo_path, repo_name in filtered_repos:
            functions = crawler.crawl_repository(repo_path, language, repo_name)
            all_results.extend(functions)
        
        # Save filtered results
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            for func in all_results:
                f.write(json.dumps(func, ensure_ascii=False) + '\n')
        
        stats_path = output_path.parent / 'crawler_statistics.json'
        print(f"\n✓ Saved {len(all_results)} functions to {output_path}")
        crawler.print_statistics()
        crawler.save_statistics(str(stats_path))
    else:
        # Crawl all repositories
        crawler.crawl_all(output_dir=args.output_dir)


if __name__ == '__main__':
    main()
