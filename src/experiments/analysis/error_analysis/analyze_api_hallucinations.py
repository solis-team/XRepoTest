"""
API Hallucination Sub-Category Analysis

This script performs post-processing analysis on errors already classified as 
"API Hallucination", breaking them down into actionable sub-categories:
- Phantom Library: Import/package-level errors (non-existent modules, classes, interfaces, or
  require paths that don't exist)
- Non-existent API: Undefined functions, methods, types, or variables that don't exist in the
  target library (including inaccessible private/protected methods and dynamic accessor failures)
- Signature Mismatch: Function/method exists but called with wrong number or type of arguments
- Other: Errors that don't fit into predefined categories

Processes error_analysis.jsonl files and generates detailed breakdown reports.
"""

import json
import re
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import Enum

from xrepotest.paths import get_evaluation_data_dir


class APISubcategory(Enum):
    """Sub-categories for API Hallucination errors"""
    PHANTOM_LIBRARY = "Phantom Library"
    NONEXISTENT_API = "Non-existent API"
    SIGNATURE_MISMATCH = "Signature Mismatch"
    OTHER = "Other"


@dataclass
class SubcategoryResult:
    """Result of sub-categorization for a single error"""
    sub_category: APISubcategory
    confidence: float
    matched_pattern: str = ""


class APIHallucinationAnalyzer:
    """Analyzer for breaking down API Hallucination errors into sub-categories"""
    
    def __init__(self, language: str):
        """
        Initialize analyzer for a specific language.
        
        Args:
            language: One of 'go', 'rust', 'julia', 'php', 'ruby'
        """
        self.language = language.lower()
        self.patterns = self._initialize_patterns()
    
    def _initialize_patterns(self) -> Dict[str, Dict[str, List[re.Pattern]]]:
        """Initialize language-specific regex patterns for sub-categorization"""
        
        # Common patterns across languages
        common = {
            'phantom_library': [
                re.compile(r'cannot find package', re.IGNORECASE),
                re.compile(r'no required module', re.IGNORECASE),
                re.compile(r'failed to resolve.*import', re.IGNORECASE),
                re.compile(r'unresolved import', re.IGNORECASE),
                re.compile(r'could not (find|load|import) (module|package)', re.IGNORECASE),
                re.compile(r'(Class|Interface|Trait).*not found', re.IGNORECASE),  # PHP class/interface/trait
                re.compile(r'LoadError.*cannot load such file', re.IGNORECASE),  # Ruby/Julia require failures
                re.compile(r'cannot load such file', re.IGNORECASE),  # Ruby LoadError body
            ],
            'nonexistent_api': [
                re.compile(r'undefined:', re.IGNORECASE),
                re.compile(r'not defined', re.IGNORECASE),
                re.compile(r'undeclared name', re.IGNORECASE),
                re.compile(r'cannot find (value|function|method|type)', re.IGNORECASE),
                re.compile(r'Call to undefined (function|method)', re.IGNORECASE),
                re.compile(r'NoMethodError', re.IGNORECASE),
                re.compile(r'NameError', re.IGNORECASE),
                re.compile(r'UndefVarError', re.IGNORECASE),
                re.compile(r'undefined variable', re.IGNORECASE),
                # Absorbed from removed Property/Reflection category
                re.compile(r'undefined (property|attribute)', re.IGNORECASE),
                re.compile(r'(property|attribute).*does not exist', re.IGNORECASE),
                re.compile(r'NoMethodError.*undefined method.*for nil', re.IGNORECASE),
            ],
            'signature_mismatch': [
                re.compile(r'wrong number of arguments', re.IGNORECASE),
                re.compile(r'expected \d+ arguments?, (got|found) \d+', re.IGNORECASE),
                re.compile(r'too (few|many) arguments', re.IGNORECASE),
                re.compile(r'cannot use .* as type', re.IGNORECASE),
                re.compile(r'no method matching', re.IGNORECASE),
                re.compile(r'MethodError.*argument', re.IGNORECASE),
                re.compile(r'mismatched types', re.IGNORECASE),
                re.compile(r'type mismatch', re.IGNORECASE),
                re.compile(r'expects parameter', re.IGNORECASE),
                re.compile(r'ArgumentError', re.IGNORECASE),
            ]
        }
        
        # Language-specific patterns
        language_specific = {
            'go': {
                'phantom_library': [
                    re.compile(r'cannot find package.*in any of', re.IGNORECASE),
                    re.compile(r'package .* is not in GOROOT', re.IGNORECASE),
                ],
                'nonexistent_api': [
                    re.compile(r'undefined(?::|(?:$|\s|\())', re.IGNORECASE),  # Match "undefined:" or "undefined " or "undefined("
                    re.compile(r'has no field or method', re.IGNORECASE),
                    re.compile(r'\w+ not declared', re.IGNORECASE),
                ],
                'signature_mismatch': [
                    re.compile(r'not enough arguments', re.IGNORECASE),
                    re.compile(r'too many arguments', re.IGNORECASE),
                    re.compile(r'cannot convert', re.IGNORECASE),
                ]
            },
            'rust': {
                'phantom_library': [
                    re.compile(r'error\[E0433\]', re.IGNORECASE),  # failed to resolve import
                    re.compile(r'error\[E0432\]', re.IGNORECASE),  # unresolved import
                    re.compile(r'can\'t find crate', re.IGNORECASE),
                ],
                'nonexistent_api': [
                    re.compile(r'error\[E0425\]', re.IGNORECASE),  # cannot find value
                    re.compile(r'error\[E0412\]', re.IGNORECASE),  # cannot find type
                    re.compile(r'error\[E0422\]', re.IGNORECASE),  # cannot find struct/enum
                    re.compile(r'error\[E0599\]', re.IGNORECASE),  # no method named
                    re.compile(r'error\[E0609\]', re.IGNORECASE),  # no field
                ],
                'signature_mismatch': [
                    re.compile(r'error\[E0308\]', re.IGNORECASE),  # mismatched types
                    re.compile(r'error\[E0061\]', re.IGNORECASE),  # wrong number of arguments
                    re.compile(r'this function takes \d+ argument', re.IGNORECASE),
                ]
            },
            'julia': {
                'phantom_library': [
                    re.compile(r'LoadError.*package .* not found', re.IGNORECASE),
                    re.compile(r'ArgumentError.*Package .* not found', re.IGNORECASE),
                ],
                'nonexistent_api': [
                    re.compile(r'UndefVarError:', re.IGNORECASE),
                    re.compile(r'undefined reference', re.IGNORECASE),
                ],
                'signature_mismatch': [
                    re.compile(r'MethodError.*no method matching', re.IGNORECASE),
                    re.compile(r'MethodError.*got \d+', re.IGNORECASE),
                ]
            },
            'php': {
                'phantom_library': [
                    re.compile(r'(Class|Interface|Trait).*not found', re.IGNORECASE),
                    re.compile(r'Failed opening required', re.IGNORECASE),
                    # PHPUnit uses "does not exist" instead of "not found" for class resolution
                    re.compile(r'(Class|Interface|class or interface).*does not exist', re.IGNORECASE),
                    re.compile(r'UnknownTypeException.*does not exist', re.IGNORECASE),
                    re.compile(r'UnknownClassOrInterfaceException', re.IGNORECASE),
                    # Missing vendor dependency (e.g., mockery PHPUnit runner not installed)
                    re.compile(r'phpunit not found', re.IGNORECASE),
                ],
                'nonexistent_api': [
                    re.compile(r'Call to undefined (function|method)', re.IGNORECASE),
                    re.compile(r'Undefined (variable|constant)', re.IGNORECASE),
                    # Dynamic accessor/mutator failures — API doesn't exist on the class
                    re.compile(r'Unknown(Setter|Getter)Exception', re.IGNORECASE),
                    re.compile(r'Unknown (setter|getter)', re.IGNORECASE),
                    re.compile(r'UnknownMethodException', re.IGNORECASE),
                    re.compile(r'Method .* does not exist', re.IGNORECASE),
                    re.compile(r'Typed property.*must not be accessed before initialization', re.IGNORECASE),
                    # PHPUnit mock configuration failures for non-existent methods
                    re.compile(r'MethodCannotBeConfiguredException.*does not exist', re.IGNORECASE),
                    re.compile(r'Trying to configure method.*does not exist', re.IGNORECASE),
                    # PHPUnit mock object limitations — hallucinated a static method on a mock
                    re.compile(r'Static method.*cannot be invoked on mock object', re.IGNORECASE),
                    re.compile(r'BadMethodCallException.*static method', re.IGNORECASE),
                    # Accessing protected/private members that don't exist in the API surface
                    re.compile(r'Cannot access (protected|private) property', re.IGNORECASE),
                    # ReflectionException for non-existent properties
                    re.compile(r'ReflectionException.*Property.*does not exist', re.IGNORECASE),
                ],
                'signature_mismatch': [
                    re.compile(r'expects (at least|at most|exactly) \d+ parameter', re.IGNORECASE),
                    re.compile(r'Missing argument \d+', re.IGNORECASE),
                ]
            },
            'ruby': {
                'phantom_library': [
                    re.compile(r'LoadError.*cannot load such file', re.IGNORECASE),
                    re.compile(r'cannot load such file', re.IGNORECASE),  # appears in full_log body
                    re.compile(r'An error occurred while loading', re.IGNORECASE),  # RSpec generic header for LoadError
                    re.compile(r'uninitialized constant.*::', re.IGNORECASE),
                ],
                'nonexistent_api': [
                    re.compile(r'NoMethodError:', re.IGNORECASE),
                    re.compile(r'NameError:', re.IGNORECASE),
                    re.compile(r'undefined (local variable|method)', re.IGNORECASE),
                    # Absorbed from removed Property/Reflection category
                    re.compile(r'undefined method.*for #<', re.IGNORECASE),  # instance-level missing method
                    re.compile(r'NoMethodError.*(private|protected) method', re.IGNORECASE),  # inaccessible method
                    re.compile(r'undefined method.*did you mean\?', re.IGNORECASE),
                ],
                'signature_mismatch': [
                    re.compile(r'wrong number of arguments', re.IGNORECASE),
                    re.compile(r'ArgumentError.*given \d+, expected \d+', re.IGNORECASE),
                ]
            }
        }
        
        # Merge common and language-specific patterns
        patterns = {}
        for category in ['phantom_library', 'nonexistent_api', 'signature_mismatch']:
            patterns[category] = common[category].copy()
            if self.language in language_specific:
                patterns[category].extend(language_specific[self.language].get(category, []))
        
        return patterns
    
    def analyze_error(self, error_message: str, log: str = "") -> SubcategoryResult:
        """
        Analyze a single API Hallucination error and determine its sub-category.
        
        Args:
            error_message: The error message from error_details
            log: Optional full log for additional context
            
        Returns:
            SubcategoryResult with sub-category and confidence
        """
        # Combine error message and log for analysis
        text_to_analyze = f"{error_message}\n{log}".lower()
        
        # Check patterns in priority order
        
        # 1. Phantom Library (highest priority - import/module/package resolution failures)
        for pattern in self.patterns['phantom_library']:
            if pattern.search(text_to_analyze):
                return SubcategoryResult(
                    sub_category=APISubcategory.PHANTOM_LIBRARY,
                    confidence=0.90,
                    matched_pattern=pattern.pattern
                )
        
        # 2. Signature Mismatch (medium priority - needs specific keywords)
        for pattern in self.patterns['signature_mismatch']:
            if pattern.search(text_to_analyze):
                return SubcategoryResult(
                    sub_category=APISubcategory.SIGNATURE_MISMATCH,
                    confidence=0.80,
                    matched_pattern=pattern.pattern
                )
        
        # 3. Non-existent API (broader patterns - check after more specific categories)
        for pattern in self.patterns['nonexistent_api']:
            if pattern.search(text_to_analyze):
                return SubcategoryResult(
                    sub_category=APISubcategory.NONEXISTENT_API,
                    confidence=0.85,
                    matched_pattern=pattern.pattern
                )
        
        # 4. Other (no clear match)
        return SubcategoryResult(
            sub_category=APISubcategory.OTHER,
            confidence=0.50,
            matched_pattern="no_match"
        )
    
    def process_file(self, error_analysis_path: Path, 
                     detailed_results_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Process an error_analysis.jsonl file and generate sub-category breakdown.
        
        Args:
            error_analysis_path: Path to error_analysis.jsonl
            detailed_results_path: Optional path to detailed_results.jsonl for logs
            
        Returns:
            Dictionary with breakdown statistics and examples
        """
        if not error_analysis_path.exists():
            raise FileNotFoundError(f"Error analysis file not found: {error_analysis_path}")
        
        # Load error analysis data
        analyses = []
        with open(error_analysis_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        analyses.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        print(f"Warning: Failed to parse line in {error_analysis_path}: {e}")
                        continue
        
        # Load detailed results for logs if available
        logs_by_task = {}
        if detailed_results_path and detailed_results_path.exists():
            with open(detailed_results_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        task_id = data.get('task_id', -1)
                        logs_by_task[task_id] = data.get('logs', [])
        
        # Process API Hallucination errors
        api_hallucinations = []
        subcategory_counts = Counter()
        subcategory_examples = defaultdict(list)
        total_api_errors = 0
        
        for analysis in analyses:
            task_id = analysis.get('task_id', -1)
            function_name = analysis.get('function_name', 'unknown')
            logs = logs_by_task.get(task_id, [])
            
            for i, error_class in enumerate(analysis.get('error_classifications', [])):
                classification = error_class.get('classification', {})
                
                # Only process API Hallucination errors
                if classification.get('error_category') == 'API Hallucination':
                    total_api_errors += 1
                    
                    error_details = classification.get('error_details', {})
                    error_message = error_details.get('error_message', '')
                    # Prefer full_log from error_details, fallback to loading from detailed_results
                    full_log = error_details.get('full_log', '')
                    if not full_log:
                        full_log = logs[i] if i < len(logs) else ""
                    
                    # Analyze and sub-categorize
                    result = self.analyze_error(error_message, full_log)
                    
                    # Track statistics
                    subcategory_counts[result.sub_category.value] += 1
                    
                    # Store examples (limit to 5 per category)
                    if len(subcategory_examples[result.sub_category.value]) < 5:
                        subcategory_examples[result.sub_category.value].append({
                            'function_name': function_name,
                            'error_message': error_message[:200],  # Truncate long messages
                            'confidence': result.confidence,
                            'matched_pattern': result.matched_pattern[:100]
                        })
                    
                    api_hallucinations.append({
                        'task_id': task_id,
                        'function_name': function_name,
                        'test_index': error_class.get('test_index', 0),
                        'sub_category': result.sub_category.value,
                        'confidence': result.confidence,
                        'original_confidence': error_details.get('confidence', 1.0)
                    })
        
        # Calculate percentages
        breakdown = {}
        for subcategory, count in subcategory_counts.items():
            percentage = (count / total_api_errors * 100) if total_api_errors > 0 else 0
            breakdown[subcategory] = {
                'count': count,
                'percentage': round(percentage, 2),
                'examples': subcategory_examples[subcategory]
            }
        
        return {
            'language': self.language,
            'total_api_hallucination_errors': total_api_errors,
            'breakdown': breakdown,
            'detailed_classifications': api_hallucinations
        }
    
    def save_results(self, results: Dict[str, Any], output_path: Path):
        """Save breakdown results to JSON file"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"[OK] Saved breakdown to {output_path}")


def process_directory_structure(language: str, mode: str, model: str, 
                                 output_root: Path) -> Optional[Dict[str, Any]]:
    """
    Process error analysis for a specific language/mode/model combination.
    
    Args:
        language: Programming language
        mode: Context mode (standard, file_context, etc.)
        model: Model name
        output_root: Root output directory
        
    Returns:
        Breakdown results or None if files not found
    """
    # Construct paths - support both old format (mode_model) and new format (mode/model)
    new_style_path = output_root / language / mode / model / "error_analysis.jsonl"
    old_style_path = output_root / language / f"{mode}_{model}" / "error_analysis.jsonl"
    
    if new_style_path.exists():
        error_analysis_path = new_style_path
        output_path = output_root / language / mode / model / "api_hallucination_breakdown.json"
    elif old_style_path.exists():
        error_analysis_path = old_style_path
        output_path = output_root / language / f"{mode}_{model}" / "api_hallucination_breakdown.json"
    else:
        print("[WARNING] Error analysis file not found in either:")
        print(f"  - {new_style_path}")
        print(f"  - {old_style_path}")
        return None
    
    detailed_results_path = get_evaluation_data_dir() / "results" / language / mode / model / "detailed_results.jsonl"
    
    print(f"\n{'='*60}")
    print(f"Processing: {language} / {mode} / {model}")
    print(f"{'='*60}")
    
    results = process_api_hallucination_breakdown(
        language=language,
        error_analysis_path=error_analysis_path,
        detailed_results_path=detailed_results_path,
        output_path=output_path,
        mode=mode,
        model=model,
    )
    
    # Print summary
    print("\nAPI Hallucination Breakdown:")
    print(f"  Total API errors: {results['total_api_hallucination_errors']}")
    for subcategory, data in results['breakdown'].items():
        print(f"  {subcategory}: {data['count']} ({data['percentage']:.1f}%)")
    
    return results


def process_api_hallucination_breakdown(
    *,
    language: str,
    error_analysis_path: Path,
    detailed_results_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
    mode: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run API Hallucination sub-category analysis for a known error analysis file.

    Args:
        language: Programming language.
        error_analysis_path: Path to error_analysis.jsonl.
        detailed_results_path: Optional path to detailed_results.jsonl for full logs.
        output_path: Optional output path; defaults to sibling api_hallucination_breakdown.json.
        mode: Optional mode metadata to include in result JSON.
        model: Optional model metadata to include in result JSON.

    Returns:
        Breakdown result dictionary.
    """
    analyzer = APIHallucinationAnalyzer(language)
    results = analyzer.process_file(error_analysis_path, detailed_results_path)

    if mode is not None:
        results['mode'] = mode
    if model is not None:
        results['model'] = model

    if output_path is None:
        output_path = error_analysis_path.parent / "api_hallucination_breakdown.json"

    analyzer.save_results(results, output_path)
    return results


def generate_validation_report(results_by_lang: Dict[str, List[Dict]], output_path: Path):
    """Generate markdown validation report with examples"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# API Hallucination Sub-Category Validation Report\n\n")
        f.write("This report shows example errors for each sub-category to validate classification accuracy.\n\n")
        
        for language, results_list in results_by_lang.items():
            f.write(f"## {language.upper()}\n\n")
            
            for results in results_list:
                mode = results.get('mode', 'unknown')
                model = results.get('model', 'unknown')
                
                f.write(f"### {mode} / {model}\n\n")
                f.write(f"**Total API Hallucination errors:** {results['total_api_hallucination_errors']}\n\n")
                
                for subcategory, data in results['breakdown'].items():
                    f.write(f"#### {subcategory} ({data['count']} errors, {data['percentage']:.1f}%)\n\n")
                    
                    if data['examples']:
                        f.write("**Examples:**\n\n")
                        for i, example in enumerate(data['examples'], 1):
                            f.write(f"{i}. **Function:** `{example['function_name']}`\n")
                            f.write(f"   - **Error:** {example['error_message']}\n")
                            f.write(f"   - **Confidence:** {example['confidence']:.2f}\n")
                            if example['matched_pattern'] != 'no_match':
                                f.write(f"   - **Pattern:** `{example['matched_pattern']}`\n")
                            f.write("\n")
                    else:
                        f.write("*No examples available*\n\n")
                
                f.write("\n")
        
        f.write(f"\n---\n*Generated: {Path.cwd()}*\n")
    
    print(f"\n[OK] Validation report saved to {output_path}")


def main():
    """Main entry point for command-line usage"""
    parser = argparse.ArgumentParser(
        description="Analyze API Hallucination errors and break them into sub-categories"
    )
    parser.add_argument('--language', '-l', type=str, 
                       help='Specific language to process')
    parser.add_argument('--mode', '-m', type=str,
                       help='Specific mode to process (standard, file_context)')
    parser.add_argument('--model', type=str,
                       help='Specific model to process')
    parser.add_argument('--output-root', type=str,
                       default='output',
                       help='Root output directory (default: output)')
    parser.add_argument('--generate-validation-report', action='store_true',
                       help='Generate validation report with examples')
    
    args = parser.parse_args()
    
    output_root = Path(args.output_root)
    
    if args.language and args.mode and args.model:
        # Process single combination
        process_directory_structure(args.language, args.mode, args.model, output_root)
    else:
        # Process all discovered results
        print("Discovering error analysis files...")
        
        supported_languages = ['go', 'rust', 'julia', 'php', 'ruby']
        supported_modes = ['standard', 'file_context']
        
        results_by_lang = defaultdict(list)
        
        for language in supported_languages:
            lang_dir = output_root / language
            if not lang_dir.exists():
                continue
            
            # Find all error_analysis.jsonl files
            for error_file in lang_dir.rglob("error_analysis.jsonl"):
                # Extract mode and model from path
                try:
                    folder_name = error_file.parent.name
                    # Expected: {mode}_{model}
                    parts = folder_name.split('_', 1)
                    if len(parts) == 2:
                        mode, model = parts
                        if mode in supported_modes:
                            result = process_directory_structure(language, mode, model, output_root)
                            if result:
                                results_by_lang[language].append(result)
                except Exception as e:
                    print(f"[WARNING] Error processing {error_file}: {e}")
        
        # Generate validation report if requested
        if args.generate_validation_report and results_by_lang:
            report_path = output_root / "api_hallucination_validation.md"
            generate_validation_report(results_by_lang, report_path)
        
        print(f"\n{'='*60}")
        print("Processing complete!")
        print(f"{'='*60}")


if __name__ == '__main__':
    main()
