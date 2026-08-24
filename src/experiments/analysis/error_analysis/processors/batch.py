"""
Batch Error Classification Pipeline

Processes evaluation results from detailed_results.jsonl files and generates
error analysis reports with category distributions and statistics.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict, Counter
from dataclasses import dataclass

from experiments.analysis.error_analysis.classifiers.go import GoErrorClassifier
from experiments.analysis.error_analysis.classifiers.julia import JuliaErrorClassifier
from experiments.analysis.error_analysis.classifiers.php import PHPErrorClassifier
from experiments.analysis.error_analysis.classifiers.ruby import RubyErrorClassifier
from experiments.analysis.error_analysis.classifiers.rust import RustErrorClassifier


@dataclass
class SampleErrorAnalysis:
    """Error analysis for a single sample"""
    task_id: int
    function_name: str
    test_count: int
    error_classifications: List[Dict[str, Any]]


class BatchErrorClassifier:
    """Batch processor for error classification across multiple evaluation results"""
    
    CLASSIFIERS = {
        'rust': RustErrorClassifier,
        'go': GoErrorClassifier,
        'julia': JuliaErrorClassifier,
        'php': PHPErrorClassifier,
        'ruby': RubyErrorClassifier,
    }
    
    def __init__(self, language: str):
        """
        Initialize batch classifier for a specific language.
        
        Args:
            language: One of 'rust', 'go', 'julia', 'php', 'ruby'
        """
        if language not in self.CLASSIFIERS:
            raise ValueError(f"Unsupported language: {language}. "
                           f"Must be one of {list(self.CLASSIFIERS.keys())}")
        
        self.language = language
        self.classifier = self.CLASSIFIERS[language]()
    
    def process_file(self, input_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a single detailed_results.jsonl file.
        
        Args:
            input_path: Path to detailed_results.jsonl
            output_dir: Directory to write output files (default: same as input)
            
        Returns:
            Dictionary containing summary statistics
        """
        input_path = Path(input_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        # Determine output directory
        if output_dir is None:
            output_dir = input_path.parent
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        
        # Read input data
        print(f"Reading {input_path}...")
        samples = []
        with open(input_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    samples.append(json.loads(line))
        
        print(f"Processing {len(samples)} samples...")
        
        # Process each sample
        all_analyses = []
        for i, sample in enumerate(samples):
            analysis = self._process_sample(sample)
            all_analyses.append(analysis)
            
            if (i + 1) % 100 == 0:
                print(f"  Processed {i + 1}/{len(samples)} samples")
        
        # Generate summary statistics
        summary = self._generate_summary(all_analyses)
        
        # Write outputs
        error_analysis_path = output_dir / 'error_analysis.jsonl'
        error_summary_path = output_dir / 'error_summary.json'
        
        self._write_detailed_results(all_analyses, error_analysis_path)
        self._write_summary(summary, error_summary_path)
        
        print("\n[OK] Results written to:")
        print(f"  - {error_analysis_path}")
        print(f"  - {error_summary_path}")
        
        return summary
    
    def _process_sample(self, sample: Dict[str, Any]) -> SampleErrorAnalysis:
        """Process a single sample and classify errors for all tests"""
        task_id = sample.get('task_id', -1)
        function_name = sample.get('function_name', 'unknown')

        def _ensure_list(value: Any) -> List[Any]:
            if value is None:
                return []
            if isinstance(value, list):
                return value
            # Many pipelines emit a single string/dict for single-test cases
            return [value]

        test_codes = _ensure_list(sample.get('test', []))
        logs = _ensure_list(sample.get('logs', []))
        checks = _ensure_list(sample.get('checks', []))
        coverage_stats = _ensure_list(sample.get('coverage_stats', []))

        # If no tests were extracted, the downstream classifier would produce
        # zero results and the sample would silently drop out of statistics.
        # Treat this as a Category-1 syntactic/preprocessing failure by
        # injecting a single synthetic test entry.
        synthetic = False
        if len(test_codes) == 0:
            synthetic = True
            test_codes = [""]
            # Prefer the classifier's explicit preprocessing branch.
            if len(logs) == 0:
                logs = ["Preprocessing: no tests generated"]
            if len(checks) == 0:
                checks = [{"compilation": False, "tests": False, "coverage": False}]
            if len(coverage_stats) == 0:
                coverage_stats = [{}]

        # Ensure per-test lists align to the number of test codes.
        target_len = len(test_codes)

        if len(logs) < target_len:
            logs = logs + [""] * (target_len - len(logs))
        elif len(logs) > target_len:
            logs = logs[:target_len]

        if len(checks) < target_len:
            checks = checks + [{}] * (target_len - len(checks))
        elif len(checks) > target_len:
            checks = checks[:target_len]

        if len(coverage_stats) < target_len:
            coverage_stats = coverage_stats + [{}] * (target_len - len(coverage_stats))
        elif len(coverage_stats) > target_len:
            coverage_stats = coverage_stats[:target_len]
        
        # Classify errors for all tests
        results = self.classifier.classify(logs, checks, coverage_stats, test_codes)
        
        # Convert to dictionaries
        error_classifications = []
        for i, result in enumerate(results):
            classification = {
                'test_index': i,
                'test_code_length': len(test_codes[i]) if i < len(test_codes) else 0,
                'classification': result.to_dict()
            }
            if synthetic:
                classification['synthetic'] = True
            error_classifications.append(classification)
        
        return SampleErrorAnalysis(
            task_id=task_id,
            function_name=function_name,
            test_count=len(test_codes),
            error_classifications=error_classifications
        )
    
    def _generate_summary(self, analyses: List[SampleErrorAnalysis]) -> Dict[str, Any]:
        """Generate summary statistics from all analyses"""
        total_samples = len(analyses)
        total_tests = sum(a.test_count for a in analyses)
        
        # Count errors by category
        category_counts = Counter()
        errors_by_sample = defaultdict(int)
        tests_with_errors = 0
        tests_without_errors = 0
        
        for analysis in analyses:
            sample_has_error = False
            for classification in analysis.error_classifications:
                result = classification['classification']
                if result['has_error']:
                    tests_with_errors += 1
                    sample_has_error = True
                    category = result['error_category']
                    if category:
                        category_counts[category] += 1
                else:
                    tests_without_errors += 1
            
            if sample_has_error:
                errors_by_sample[analysis.task_id] += 1
        
        # Calculate rates
        error_rate = tests_with_errors / total_tests if total_tests > 0 else 0
        samples_with_errors = len(errors_by_sample)
        sample_error_rate = samples_with_errors / total_samples if total_samples > 0 else 0
        
        # Category distribution with both percentage metrics
        category_distribution = {
            category: {
                'count': count,
                'percentage_of_errors': (count / tests_with_errors * 100) if tests_with_errors > 0 else 0,
                'percentage_of_total_tests': (count / total_tests * 100) if total_tests > 0 else 0
            }
            for category, count in category_counts.items()
        }
        
        summary = {
            'language': self.language,
            'total_samples': total_samples,
            'total_tests': total_tests,
            'tests_with_errors': tests_with_errors,
            'tests_without_errors': tests_without_errors,
            'error_rate': error_rate,
            'samples_with_errors': samples_with_errors,
            'sample_error_rate': sample_error_rate,
            'category_distribution': category_distribution,
            'category_counts': dict(category_counts)
        }
        
        return summary
    
    def _write_detailed_results(self, analyses: List[SampleErrorAnalysis], 
                                output_path: Path):
        """Write detailed error analysis to JSONL file"""
        with open(output_path, 'w', encoding='utf-8') as f:
            for analysis in analyses:
                record = {
                    'task_id': analysis.task_id,
                    'function_name': analysis.function_name,
                    'test_count': analysis.test_count,
                    'error_classifications': analysis.error_classifications
                }
                f.write(json.dumps(record) + '\n')
    
    def _write_summary(self, summary: Dict[str, Any], output_path: Path):
        """Write summary statistics to JSON file"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        
        # Also print summary to console
        print("\n" + "="*60)
        print("ERROR CLASSIFICATION SUMMARY")
        print("="*60)
        print(f"Language: {summary['language']}")
        print(f"Total Samples: {summary['total_samples']}")
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Tests with Errors: {summary['tests_with_errors']} "
              f"({summary['error_rate']*100:.1f}%)")
        print(f"Tests without Errors: {summary['tests_without_errors']}")
        print(f"Samples with Errors: {summary['samples_with_errors']} "
              f"({summary['sample_error_rate']*100:.1f}%)")
        print("\nError Category Distribution:")
        print(f"  {'Category':<35}   {'Count':>5}   {'% of Errors':>10}   {'% of Tests':>10}")
        print(f"  {'-'*35}   {'-'*5}   {'-'*10}   {'-'*10}")
        for category, stats in sorted(summary['category_distribution'].items(),
                                      key=lambda x: x[1]['count'], reverse=True):
            print(f"  {category:<35} - {stats['count']:>5}   {stats['percentage_of_errors']:>9.1f}%   {stats['percentage_of_total_tests']:>9.1f}%")
        print("="*60)


def process_directory(input_dir: str, language: str, 
                     output_base_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Process all detailed_results.jsonl files in a directory tree.
    
    Args:
        input_dir: Root directory to search for detailed_results.jsonl
        language: Language to process
        output_base_dir: Base directory for outputs (default: same structure as input)
        
    Returns:
        Dictionary mapping file paths to their summaries
    """
    input_dir = Path(input_dir)
    classifier = BatchErrorClassifier(language)
    
    # Find all detailed_results.jsonl files
    result_files = list(input_dir.rglob('detailed_results.jsonl'))
    
    if not result_files:
        print(f"No detailed_results.jsonl files found in {input_dir}")
        return {}
    
    print(f"Found {len(result_files)} file(s) to process")
    
    all_summaries = {}
    for i, result_file in enumerate(result_files, 1):
        print(f"\n[{i}/{len(result_files)}] Processing: {result_file}")
        
        # Determine output directory
        if output_base_dir:
            relative_path = result_file.parent.relative_to(input_dir)
            output_dir = Path(output_base_dir) / relative_path
        else:
            output_dir = result_file.parent
        
        try:
            summary = classifier.process_file(str(result_file), str(output_dir))
            all_summaries[str(result_file)] = summary
        except Exception as e:
            print(f"  ✗ Error processing {result_file}: {e}")
            continue
    
    print(f"\n[OK] Successfully processed {len(all_summaries)}/{len(result_files)} files")
    
    return all_summaries
