"""
LLM Test Generation and Evaluation Pipeline - Two Phase Approach

Phase 1: Generate test cases and save to files
Phase 2: Read test cases from files and evaluate them

This module integrates with OpenAI and Google Gemini APIs to generate test cases
and evaluate their coverage on canonical solutions.

Supported providers:
- OpenAI: gpt-4, gpt-4-turbo, gpt-3.5-turbo, etc.
- Google Gemini: gemini-pro, gemini-1.5-pro, gemini-1.5-flash, etc.
"""

import os
import json
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from evaluators import evaluate_llm_test_generations
from comment_stripper import strip_comments

def get_test_generation_prompt(language, canonical_solution, instruction):
    language_lower = language.lower()
    if language_lower == "php":
        return f"""Given this {language} code solution:
        ```php
        {canonical_solution}
        ```

        Task description: {instruction}

        Generate comprehensive test cases for this code. Include edge cases and various inputs.
        Requirements:
        - Use PHPUnit Framework for testing
        - Define at least one test class that extends TestCase
        - Each test must be inside a public function test*() method
        - Use only PHPUnit assertions (e.g. assertTrue, assertFalse, assertEquals, assertSame)
        - Do NOT use PHP built-in assert()
        - Do NOT include explanations, comments, or non-test code
        - Output only valid PHPUnit test code
        """
        
    elif language_lower == "ruby":
        return f"""Given this {language} code solution:

            ```ruby
            {canonical_solution}
            ```

            Task description: {instruction}

            Generate comprehensive test cases for the Ruby code above using the Minitest framework. Requirements:
            - Use Minitest::Test
            - Define at least one test class that inherits from Minitest::Test
            - Use only Minitest assertions (e.g. assert, assert_equal, assert_nil, assert_raises)
            - Do NOT use RSpec (describe, it, expect, etc.)
            - Do NOT include explanations or comments
            - Output only valid Ruby test code
            """
    else:
        # Default for Go, Julia, Rust, etc.
        return f"""Given this {language} code solution:
        ```{language_lower}
        {canonical_solution}
        ```

        Task description: {instruction}

        Requirement:
        - Generate comprehensive test cases for this code. Include edge cases and various inputs.
        - Generate only the test code without explanations. The tests should verify the correctness of the solution.
        - DO NOT rewrite, copy, or reimplement the focal function(s)."""


def generate_tests_with_gemini(task_data: List[Dict], 
                              model: str = "gemini-pro",
                              max_workers: int = 1,
                              max_retries: int = 3,
                              retry_delay: float = 1.0,
                              request_delay: float = 8.0) -> List[str]:
    """
    Generate test cases using Google Gemini API with multithreading
    
    Args:
        task_data: List of task dictionaries containing canonical_solution
        model: Gemini model to use (e.g., 'gemini-pro', 'gemini-1.5-pro', 'gemini-1.5-flash')
        max_workers: Maximum number of concurrent threads
        max_retries: Maximum number of retry attempts for failed API calls
        retry_delay: Initial delay in seconds between retries (uses exponential backoff)
        request_delay: Delay in seconds after each successful request (helps with free tier quota)
        
    Returns:
        List of generated test code
    """
    import google.generativeai as genai
    
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable must be set")
    
    # Configure Gemini
    genai.configure(api_key=api_key)
    
    # Thread-safe print lock
    print_lock = threading.Lock()
    
    def generate_single_test(task: Dict) -> tuple[int, str]:
        """Generate test for a single task with retry logic"""
        language = task['task_id'].split('/')[0]
        canonical_solution = task.get('prompt', '') + '\n' + task.get('canonical_solution', '')
        instruction = task.get('instruction', task.get('prompt', ''))
        


        prompt = get_test_generation_prompt(language, canonical_solution, instruction)
        
        
        last_error = None
        for attempt in range(max_retries):
            try:
                # Create model instance
                gemini_model = genai.GenerativeModel(model)
                
                # Generate response
                response = gemini_model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        temperature=0.3,
                    )
                )
                
                # Add delay after successful request to avoid quota limits
                if request_delay > 0:
                    time.sleep(request_delay)
                
                return task_data.index(task), response.text
            
            except Exception as e:
                last_error = e
                error_str = str(e)
                
                # Check if it's a retryable error
                should_retry = any([
                    "rate_limit" in error_str.lower(),
                    "quota" in error_str.lower(),
                    "429" in error_str,
                    "500" in error_str,
                    "502" in error_str,
                    "503" in error_str,
                    "504" in error_str,
                    "timeout" in error_str.lower(),
                    "connection" in error_str.lower(),
                    "api" in error_str.lower(),
                    "network" in error_str.lower()
                ])
                
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    thread_id = threading.current_thread().name
                    with print_lock:
                        if should_retry:
                            print(f"  [{thread_id}] Retry {attempt + 1}/{max_retries} for {task['task_id']} - Error: {error_str[:80]}")
                        else:
                            print(f"  [{thread_id}] Retry {attempt + 1}/{max_retries} for {task['task_id']} - Non-retryable error, trying anyway: {error_str[:80]}")
                        print(f"  [{thread_id}] Waiting {wait_time:.1f}s before retry...")
                    time.sleep(wait_time)
                else:
                    with print_lock:
                        print(f"  ✗ Max retries reached for {task['task_id']}: {error_str[:100]}")
                    break
        
        return task_data.index(task), f"Error after {max_retries} attempts: {str(last_error)}"
    
    generated_tests = [None] * len(task_data)
    
    print(f"  Using multithreading with {max_workers} workers...")
    if request_delay > 0:
        print(f"  Request delay: {request_delay}s per request")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(generate_single_test, task): task
            for task in task_data
        }
        
        completed = 0
        for future in as_completed(future_to_task):
            try:
                idx, test_code = future.result()
                generated_tests[idx] = test_code
                completed += 1
                
                task = future_to_task[future]
                with print_lock:
                    if test_code and not test_code.startswith("Error"):
                        print(f"  ✓ [{completed}/{len(task_data)}] Completed: {task['task_id']}")
                    else:
                        print(f"  ✗ [{completed}/{len(task_data)}] Failed: {task['task_id']}")
            except Exception as e:
                task = future_to_task[future]
                idx = task_data.index(task)
                with print_lock:
                    print(f"  ✗ Exception processing {task['task_id']}: {str(e)}")
                generated_tests[idx] = f"Exception: {str(e)}"
    
    return generated_tests

def generate_tests_with_openai(task_data: List[Dict], 
                              model: str = "gpt-4",
                              base_url: Optional[str] = None,
                              max_workers: int = 5,
                              max_retries: int = 3,
                              retry_delay: float = 1.0) -> List[str]:
    """
    Generate test cases using OpenAI API with multithreading
    
    Args:
        task_data: List of task dictionaries containing canonical_solution
        model: OpenAI model to use
        base_url: Optional custom base URL for OpenAI API
        max_workers: Maximum number of concurrent threads
        max_retries: Maximum number of retry attempts for failed API calls
        retry_delay: Initial delay in seconds between retries (uses exponential backoff)
        
    Returns:
        List of generated test code
    """
    from openai import OpenAI
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable must be set")
    
    # Initialize client with optional base_url
    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    
    client = OpenAI(**client_kwargs)
    
    # Thread-safe print lock to prevent interleaved output
    print_lock = threading.Lock()
    
    def generate_single_test(task: Dict) -> tuple[int, str]:
        """Generate test for a single task with retry logic"""
        # Extract language from task_id
        language = task['task_id'].split('/')[0]
        canonical_solution = task.get('prompt', '') + '\n' + task.get('canonical_solution', '')
        instruction = task.get('instruction', task.get('prompt', ''))
        
        # Create prompt for test generation
        prompt = get_test_generation_prompt(language, canonical_solution, instruction)
        
        messages = [
            {"role": "system", "content": f"You are an expert {language} programmer specializing in writing comprehensive test cases."},
            {"role": "user", "content": prompt}
        ]
        
        last_error = None
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.3
                )
                return task_data.index(task), response.choices[0].message.content
            
            except Exception as e:
                last_error = e
                error_str = str(e)
                
                # Check if it's a rate limit or server error that we should retry
                should_retry = any([
                    "rate_limit" in error_str.lower(),
                    "429" in error_str,
                    "500" in error_str,
                    "502" in error_str,
                    "503" in error_str,
                    "504" in error_str,
                    "timeout" in error_str.lower(),
                    "connection" in error_str.lower(),
                    "api" in error_str.lower(),
                    "network" in error_str.lower()
                ])
                
                if attempt < max_retries - 1:
                    # Exponential backoff: wait longer after each retry
                    wait_time = retry_delay * (2 ** attempt)
                    thread_id = threading.current_thread().name
                    with print_lock:
                        if should_retry:
                            print(f"  [{thread_id}] Retry {attempt + 1}/{max_retries} for {task['task_id']} - Error: {error_str[:80]}")
                        else:
                            print(f"  [{thread_id}] Retry {attempt + 1}/{max_retries} for {task['task_id']} - Non-retryable error, trying anyway: {error_str[:80]}")
                        print(f"  [{thread_id}] Waiting {wait_time:.1f}s before retry...")
                    time.sleep(wait_time)
                else:
                    # Max retries reached
                    with print_lock:
                        print(f"  ✗ Max retries reached for {task['task_id']}: {error_str[:100]}")
                    break
        
        # Return error message if all retries failed
        return task_data.index(task), f"Error after {max_retries} attempts: {str(last_error)}"
    
    generated_tests = [None] * len(task_data)
    
    print(f"  Using multithreading with {max_workers} workers...")
    
    # Process tasks concurrently using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_task = {
            executor.submit(generate_single_test, task): task
            for task in task_data
        }
        
        # Collect results as they complete
        completed = 0
        for future in as_completed(future_to_task):
            try:
                idx, test_code = future.result()
                generated_tests[idx] = test_code
                completed += 1
                
                task = future_to_task[future]
                with print_lock:
                    if test_code and not test_code.startswith("Error"):
                        print(f"  ✓ [{completed}/{len(task_data)}] Completed: {task['task_id']}")
                    else:
                        print(f"  ✗ [{completed}/{len(task_data)}] Failed: {task['task_id']}")
            except Exception as e:
                task = future_to_task[future]
                idx = task_data.index(task)
                with print_lock:
                    print(f"  ✗ Exception processing {task['task_id']}: {str(e)}")
                generated_tests[idx] = f"Exception: {str(e)}"
    
    return generated_tests


def generate_and_save_tests(language_data: Dict[str, List],
                           model: str = "gpt-4",
                           output_dir: str = "generated_tests",
                           limit_per_language: Optional[int] = None,
                           base_url: Optional[str] = None,
                           max_workers: int = 5,
                           max_retries: int = 3,
                           retry_delay: float = 1.0) -> str:
    """
    Phase 1: Generate test cases with LLM and save to JSONL files
    
    Tests are saved in: {output_dir}/{language}/{model}/generated.jsonl
    
    Args:
        language_data: Dict mapping language to task data (with canonical_solution)
        model: Model name (e.g., 'gpt-4', 'gemini-pro', 'gemini-1.5-flash')
        output_dir: Directory to save generated tests
        limit_per_language: Limit number of tasks per language for testing
        base_url: Optional custom base URL for OpenAI API (e.g., "https://ai.megallm.io/v1")
                  Only used for OpenAI models
        max_workers: Maximum number of concurrent threads (default: 5)
        max_retries: Maximum number of retry attempts for failed API calls (default: 3)
        retry_delay: Initial delay in seconds between retries (default: 1.0)
        
    Returns:
        Path to the output directory
    """
    # Limit data if specified
    if limit_per_language:
        language_data = {
            lang: tasks[:limit_per_language]
            for lang, tasks in language_data.items()
        }
    
    # Sanitize model name for file path
    model_name = model.replace('/', '_').replace(':', '_')
    
    # Detect provider
    is_gemini = model.startswith('gemini')
    provider = "Google Gemini" if is_gemini else "OpenAI"
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print(f"Saving generated tests to: {output_path}")
    print(f"Provider: {provider}")
    print(f"Model: {model}")
    if base_url and not is_gemini:
        print(f"Base URL: {base_url}")
    print(f"Max workers: {max_workers}")
    print("="*60)
    
    # Save global metadata
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    metadata = {
        'timestamp': timestamp,
        'model': model,
        'model_sanitized': model_name,
        'base_url': base_url,
        'max_workers': max_workers,
        'languages': list(language_data.keys()),
        'total_tasks': sum(len(tasks) for tasks in language_data.values())
    }
    
    metadata_file = output_path / f"metadata_{model_name}_{timestamp}.json"
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Generate and save test cases for each language
    for lang, tasks in language_data.items():
        print(f"\nGenerating {lang} test cases with {model}...")
        
        # Create language/model directory
        lang_model_dir = output_path / lang / model_name
        lang_model_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate tests with appropriate provider
        if is_gemini:
            tests = generate_tests_with_gemini(
                tasks,
                model=model,
                max_workers=max_workers,
                max_retries=max_retries,
                retry_delay=retry_delay
            )
        else:
            tests = generate_tests_with_openai(
                tasks, 
                model=model, 
                base_url=base_url,
                max_workers=max_workers,
                max_retries=max_retries,
                retry_delay=retry_delay
            )
        
        # Save as JSONL file
        jsonl_file = lang_model_dir / "generated.jsonl"
        with open(jsonl_file, 'w', encoding='utf-8') as f:
            for task, test_code in zip(tasks, tests):
                # Handle None values (failed generations)
                if test_code is None:
                    test_code = "Error: Test generation failed (returned None)"
                
                prompt_signature = task.get('prompt', '')  # Extract only the signature line
                canonical_solution = prompt_signature + '\n' + task.get('canonical_solution', '')
                # Strip comments from canonical solution for saving
                canonical_solution = strip_comments(canonical_solution, lang)
                print(f"Prompt Signature:\n{prompt_signature}\n")
                task_output = {
                    'task_id': task['task_id'],
                    'generated_test': test_code,
                    'canonical_solution': canonical_solution,
                    'instruction': task.get('instruction', task.get('prompt', '')),
                    'model': model
                }
                f.write(json.dumps(task_output, ensure_ascii=False) + '\n')
        
        # Count successful vs failed
        successful = sum(1 for t in tests if t and not t.startswith("Error") and not t.startswith("Exception"))
        failed = len(tests) - successful
        
        print(f"  ✓ Saved {len(tests)} test cases to {jsonl_file}")
        print(f"    Success: {successful}, Failed: {failed}")
    
    print("\n" + "="*60)
    print(f"Phase 1 Complete: All tests saved to {output_path}")
    print("="*60)
    
    return str(output_path)


def load_and_evaluate_tests(input_dir: str, 
                            model: Optional[str] = None) -> Dict:
    """
    Phase 2: Load generated tests from JSONL files and evaluate them
    
    Coverage measurement is always enabled.
    Results are automatically saved to {language}/{model_name}_evaluation.json
    
    Args:
        input_dir: Directory containing generated tests
        model: Optional model name to evaluate (if not specified, evaluates all models)
        
    Returns:
        Evaluation results with test pass rates and coverage statistics
    """
    measure_coverage = True
    extract_tests = True
    input_path = Path(input_dir)
    
    if not input_path.exists():
        raise ValueError(f"Input directory does not exist: {input_dir}")
    
    print(f"Loading tests from: {input_path}")
    print("="*60)
    
    # Load test cases by language
    language_data = {}
    generated_tests = {}
    model_info = {}
    
    for lang_dir in input_path.iterdir():
        if not lang_dir.is_dir():
            continue
        
        lang = lang_dir.name
        print(f"\nLoading {lang} tests...")
        
        # Look for model subdirectories
        model_dirs = [d for d in lang_dir.iterdir() if d.is_dir()]
        
        if not model_dirs:
            print(f"  No model directories found in {lang_dir}")
            continue
        
        # Filter by model if specified
        if model:
            model_sanitized = model.replace('/', '_').replace(':', '_')
            model_dirs = [d for d in model_dirs if d.name == model_sanitized]
            if not model_dirs:
                print(f"  No directory found for model {model}")
                continue
        
        for model_dir in model_dirs:
            model_name = model_dir.name
            jsonl_file = model_dir / "generated.jsonl"
            
            if not jsonl_file.exists():
                print(f"  No generated.jsonl found in {model_dir}")
                continue
            
            tasks = []
            tests = []
            
            print(f"  Loading {lang}/{model_name}/generated.jsonl...")
            
            # Load JSONL file
            with open(jsonl_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        task_data = json.loads(line)
                        tasks.append(task_data)
                        # Handle None values from old/corrupted files
                        test_code = task_data.get('generated_test')
                        if test_code is None:
                            test_code = "Error: Test generation failed (None value in file)"
                        tests.append(test_code)
            
            # Use combined key: language_modelname
            combined_key = f"{lang}_{model_name}"
            language_data[combined_key] = tasks
            generated_tests[combined_key] = tests
            model_info[combined_key] = {
                'model': task_data.get('model', model_name) if tasks else model_name,
                'model_dir': model_name,
                'language': lang
            }
            
            print(f"    ✓ Loaded {len(tasks)} test cases")
    
    # Evaluate all generated tests
    print("\n" + "="*60)
    print(f"Evaluating test coverage on canonical solutions {lang}...")
    print("="*60)
    
    # Note: extract_tests=True because generated tests may contain markdown formatting
    # The test extractor will handle extracting clean test code
    results = evaluate_llm_test_generations(
        language_data, 
        generated_tests, 
        measure_coverage=True,
        extract_tests=True,
        log_file=f'{lang}_llm_evaluation_log.txt'
    )
    
    # Display results
    print("\n" + "="*60)
    print("Evaluation Results")
    print("="*60)
    print(f"Total evaluated: {results['total_evaluated']}")
    print(f"Total tests passed: {results['total_tests_passed']}")
    if results['total_evaluated'] > 0:
        pass_rate = results['total_tests_passed'] / results['total_evaluated'] * 100
        print(f"Overall test pass rate: {pass_rate:.2f}%")
    
    # Display coverage stats if available
    if measure_coverage and results.get('coverage_stats'):
        print("\n" + "="*60)
        print("Test Coverage Statistics")
        print("="*60)
        for lang, stats in results['coverage_stats'].items():
            print(f"\n{lang}:")
            print(f"  Average coverage: {stats['average']:.2f}%")
            print(f"  Min coverage: {stats['min']:.2f}%")
            print(f"  Max coverage: {stats['max']:.2f}%")
            # print(f"  Tests measured: {stats['count']}")
    
    # Display extraction stats
    if results.get('extraction_stats'):
        print("\n" + "="*60)
        print("Test Extraction Statistics")
        print("="*60)
        for lang, stats in results['extraction_stats'].items():
            print(f"\n{lang}:")
            print(f"  Extraction success rate: {stats['extraction_rate']*100:.2f}%")
            print(f"  Average confidence: {stats['average_confidence']*100:.2f}%")
            # print(f"  Tests extracted: {stats['count']}")
    
    # Save evaluation results by language and model
    print("\n" + "="*60)
    print("Saving evaluation results...")
    print("="*60)
    
    for lang_key, info in model_info.items():
        lang = info['language']
        model_dir = info['model_dir']
        
        # Get results for this language
        lang_results = {
            'language': lang,
            'model': info['model'],
            'evaluation_timestamp': datetime.now().isoformat(),
            'total_evaluated': len(language_data[lang_key]),
            'test_pass_rate': results['test_pass_rates'].get(lang_key, 0),
            'coverage_stats': results['coverage_stats'].get(lang_key, {}),
            # 'extraction_stats': results['extraction_stats'].get(lang_key, {})
        }
        
        # Save to language/model/evaluation.json
        eval_dir = input_path / lang / model_dir
        eval_file = eval_dir / "evaluation.json"
        
        with open(eval_file, 'w') as f:
            json.dump(lang_results, f, indent=2)
        
        print(f"  ✓ Saved {lang}/{model_dir} results to {eval_file}")
    
    # Also save overall summary
    summary_file = input_path / "evaluation_summary.json"
    
    # Prepare results for JSON (remove detailed_results for brevity)
    summary_results = {
        'input_dir': str(input_path),
        'evaluation_timestamp': datetime.now().isoformat(),
        'total_evaluated': results['total_evaluated'],
        'total_tests_passed': results['total_tests_passed'],
        'overall_pass_rate': results['total_tests_passed'] / results['total_evaluated'] * 100 if results['total_evaluated'] > 0 else 0,
        'test_pass_rates': results['test_pass_rates'],
        'coverage_stats': results['coverage_stats'],
        # 'extraction_stats': results['extraction_stats'],
        'models_evaluated': {k: v['model'] for k, v in model_info.items()}
    }
    
    with open(summary_file, 'w') as f:
        json.dump(summary_results, f, indent=2)
    
    print(f"  ✓ Saved overall summary to {summary_file}")
    
    print(f"{'='*60}")
    
    return results


