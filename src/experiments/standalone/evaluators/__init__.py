"""
Language Evaluators Package

Language-specific evaluators for test execution and coverage measurement
"""

import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from experiments.standalone.evaluators.base_evaluator import LanguageEvaluator
from experiments.standalone.evaluators.ruby_evaluator import RubyEvaluator
from experiments.standalone.evaluators.julia_evaluator import JuliaEvaluator
from experiments.standalone.evaluators.go_evaluator import GoEvaluator
from experiments.standalone.evaluators.rust_evaluator import RustEvaluator
from experiments.standalone.evaluators.php_evaluator import PHPEvaluator


def get_language_evaluator(language: str) -> LanguageEvaluator:
    """Get the appropriate evaluator for the given language"""
    evaluators = {
        'Ruby': RubyEvaluator,
        'Julia': JuliaEvaluator,
        'Go': GoEvaluator,
        'Rust': RustEvaluator,
        'PHP': PHPEvaluator
    }
    
    evaluator_class = evaluators.get(language)
    if evaluator_class is None:
        raise ValueError(f"Unsupported language: {language}")
    
    return evaluator_class()


def evaluate_single_test(raw_response: str,
                         task_data: Dict,
                         test_extractor,
                         measure_coverage: bool = True,
                         extract_test: bool = True,
                         log_file: Optional[str] = None) -> Dict:
    """
    Evaluate a single LLM-generated test case
    
    Args:
        raw_response: Raw LLM response (may contain markdown)
        task_data: Dictionary with task_id, canonical_solution, etc.
        test_extractor: TestExtractor instance
        measure_coverage: Whether to measure coverage
        extract_test: Whether to extract test code from response
        log_file: Optional path to log file for detailed debugging
        
    Returns:
        Evaluation results dictionary
    """
    # Extract language from task_id
    language = task_data['task_id'].split('/')[0]
    canonical_code = task_data.get('prompt', '') + task_data.get('canonical_solution', '')
    
    def log_message(msg: str):
        if log_file:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(msg + '\n')
    
    log_message(f"\n{'='*80}")
    log_message(f"Evaluating: {task_data['task_id']}")
    log_message(f"Language: {language}")
    log_message(f"{'='*80}")
    
    if not canonical_code:
        log_message("ERROR: No canonical solution provided")
        return {
            'task_id': task_data['task_id'],
            'language': language,
            'error': 'No canonical solution provided',
            'test_success': False,
            'coverage': None,
            'extraction_valid': False
        }
    
    # Extract test code from raw response if needed
    log_message("\nStep 1: Test Extraction")
    log_message(f"Raw response length: {len(raw_response)} chars")
    log_message(f"Raw response preview: {raw_response[:200]}...")
    
    if extract_test:
        generated_test = test_extractor.extract_test_code(raw_response, language)
        validation = test_extractor.validate_test_code(generated_test, language)
        log_message(f"Extracted test length: {len(generated_test)} chars")
        log_message(f"Validation: valid={validation['valid']}, confidence={validation.get('confidence', 0.0)}")
    else:
        generated_test = raw_response
        validation = {'valid': True, 'confidence': 1.0}
        log_message("Using raw response as test (no extraction)")
    
    log_message(f"\nExtracted Test Code:\n{'-'*80}")
    log_message(generated_test)
    log_message(f"{'-'*80}")
    
    # Get language-specific evaluator
    log_message("\nStep 2: Prepare Test File")
    lang_evaluator = get_language_evaluator(language)
    log_message(f"Using evaluator: {lang_evaluator.__class__.__name__}")
    
    # Prepare test file with canonical solution and tests
    log_message(f"{'-'*80}")
    log_message(canonical_code)
    log_message(f"{'-'*80}")
    log_message(generated_test)
    log_message(f"{'-'*80}")
    test_content = lang_evaluator.prepare_test_file(" ", generated_test)
    log_message(f"\nPrepared Test File Content:\n{'-'*80}")
    log_message(test_content)
    log_message(f"{'-'*80}")
    
    # Create temporary files for testing
    # 1. Focal file containing canonical solution
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix=lang_evaluator.get_file_extension(),
        delete=False,
        prefix='focal_'
    ) as focal_file:
        focal_file.write(canonical_code)
        focal_file_path = focal_file.name
    
    # 2. Test file containing both solution and tests


    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix=lang_evaluator.get_file_extension(),
        delete=False,
        prefix='test_'
    ) as tmp_file:
        tmp_file.write(test_content)
        tmp_file_path = tmp_file.name
    
    try:
        # log_message("\nStep 3: Compilation (if needed)")
        # # Compile if needed
        # compile_success, compile_error = lang_evaluator.compile_if_needed(tmp_file_path)
        # log_message(f"Compile success: {compile_success}")
        # if compile_error:
        #     log_message(f"Compile output/error: {compile_error}")
        
        # if not compile_success:
        #     log_message("RESULT: Compilation failed")
        #     return {
        #         'task_id': task_data['task_id'],
        #         'language': language,
        #         'test_success': False,
        #         'test_output': '',
        #         'test_error': f'Compilation failed: {compile_error}',
        #         'coverage': None,
        #         'generated_test': generated_test[:200] + '...' if len(generated_test) > 200 else generated_test,
        #         'extraction_valid': validation['valid'],
        #         'extraction_confidence': validation.get('confidence', 0.0),
        #         'canonical_solution': canonical_code[:100] + '...' if len(canonical_code) > 100 else canonical_code
        #     }
        
        # Run tests
        log_message("\nStep 4: Run Tests")
        test_success, test_stdout, test_stderr = lang_evaluator.run_tests(focal_file_path, tmp_file_path)
        log_message(f"Test success: {test_success}")
        log_message(f"Test stdout:\n{test_stdout}")
        log_message(f"Test stderr:\n{test_stderr}")
        

        # Measure coverage if requested (even if tests fail, we can still measure coverage)
        coverage = None
        covered_lines = 0
        total_lines = 0
        if measure_coverage and validation['valid']:
            log_message("\nStep 5: Measure Coverage")
            covered_lines, total_lines = lang_evaluator.measure_coverage(focal_file_path, tmp_file_path)
            if total_lines > 0:
                coverage = round((covered_lines / total_lines) * 100, 2)
                log_message(f"Coverage: {coverage}% ({covered_lines}/{total_lines} lines)")
            else:
                log_message("Coverage: None")
        
        log_message(f"\nFINAL RESULT: {'PASS' if test_success else 'FAIL'}")
        
    finally:
        # Clean up temporary files
        try:
            Path(focal_file_path).unlink(missing_ok=True)
            Path(tmp_file_path).unlink(missing_ok=True)
            # Also remove compiled outputs if any
            Path(tmp_file_path + '.out').unlink(missing_ok=True)
            Path(focal_file_path + '.out').unlink(missing_ok=True)
        except:
            pass
    
    # Evaluation result
    result = {
        'task_id': task_data['task_id'],
        'language': language,
        'test_success': test_success,
        'test_output': test_stdout,
        'test_error': test_stderr,
        'coverage': coverage,
        'covered_lines': covered_lines,
        'total_lines': total_lines,
        'generated_test': generated_test[:200] + '...' if len(generated_test) > 200 else generated_test,
        'extraction_valid': validation['valid'],
        'extraction_confidence': validation.get('confidence', 0.0),
        'canonical_solution': canonical_code[:100] + '...' if len(canonical_code) > 100 else canonical_code
    }
    
    return result


def evaluate_tests_batch(raw_responses: List[str],
                         task_data_list: List[Dict],
                         test_extractor,
                         measure_coverage: bool = True,
                         extract_test: bool = True,
                         log_file: Optional[str] = None) -> List[Dict]:
    """
    Evaluate multiple test generations in batch
    
    Args:
        raw_responses: List of raw LLM responses
        task_data_list: List of task data dictionaries
        test_extractor: TestExtractor instance
        measure_coverage: Whether to measure coverage
        extract_test: Whether to extract test code
        
    Returns:
        List of evaluation results
    """
    results = []
    for response, task_data in zip(raw_responses, task_data_list):
        result = evaluate_single_test(
            response,
            task_data,
            test_extractor,
            measure_coverage=measure_coverage,
            extract_test=extract_test,
            log_file=log_file
        )
        results.append(result)
    
    return results


def evaluate_llm_test_generations(language_data: Dict[str, List],
                                 generated_responses: Dict[str, List[str]],
                                 measure_coverage: bool = True,
                                 extract_tests: bool = True,
                                 log_file: Optional[str] = None) -> Dict:
    """
    Main evaluation pipeline for LLM-generated tests
    
    Args:
        language_data: Dict mapping language name to list of task data
        generated_responses: Dict mapping language name to list of raw LLM responses
        measure_coverage: Whether to measure test coverage
        extract_tests: Whether to extract test code from responses
        
    Returns:
        Evaluation results and statistics
    """
    from test_extractor import TestExtractor
    
    test_extractor = TestExtractor()
    all_results = []
    
    for lang, tasks in language_data.items():
        if lang not in generated_responses:
            print(f"Warning: No generated responses for {lang}")
            continue
        
        print(f"Evaluating {lang} tests...")
        results = evaluate_tests_batch(
            generated_responses[lang],
            tasks,
            test_extractor,
            measure_coverage=measure_coverage,
            extract_test=extract_tests,
            log_file=log_file
        )
        all_results.extend(results)
        
        # Show progress
        passed = sum(1 for r in results if r.get('test_success', False) and 'error' not in r)
        print(f"  {passed}/{len(results)} tests passed")
    
    # Calculate statistics
    total_evaluated = len(all_results)
    total_passed = sum(1 for r in all_results if r.get('test_success', False) and 'error' not in r)
    
    # Calculate pass rates by language
    pass_rates = {}
    for lang in language_data.keys():
        lang_results = [r for r in all_results if r.get('language', '').startswith(lang.split('_')[0])]
        if lang_results:
            passed = sum(1 for r in lang_results if r.get('test_success', False) and 'error' not in r)
            pass_rates[lang] = passed / len(lang_results) if lang_results else 0.0
    
    # Calculate coverage statistics
    coverage_stats = {}
    for lang in language_data.keys():
        lang_results = [r for r in all_results if r.get('language', '').startswith(lang.split('_')[0])]
        covered_lines = [r['covered_lines'] for r in lang_results if r.get('covered_lines') is not None]
        total_lines = [r['total_lines'] for r in lang_results if r.get('total_lines') is not None]
        if covered_lines:
            coverage_stats[lang] =  sum(covered_lines) / sum(total_lines) * 100 if total_lines else 0.0,

    
    return {
        'detailed_results': all_results,
        'test_pass_rates': pass_rates,
        'coverage_stats': coverage_stats,
        'total_evaluated': total_evaluated,
        'total_tests_passed': total_passed
    }


__all__ = [
    'LanguageEvaluator',
    'RubyEvaluator',
    'JuliaEvaluator',
    'GoEvaluator',
    'RustEvaluator',
    'PHPEvaluator',
    'get_language_evaluator',
    'evaluate_single_test',
    'evaluate_tests_batch',
    'evaluate_llm_test_generations'
]
