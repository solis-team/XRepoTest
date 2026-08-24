"""
Unified Generation Script

This script reads prompts from JSONL files and generates responses using an OpenAI-compatible API.
It supports both:
1. Native OpenAI API (GPT-4, GPT-3.5)
2. Self-hosted vLLM server (compatible with OpenAI API)

Usage:
    # For OpenAI
    python run_generation.py --model gpt-3.5-turbo --api_keysk-...

    # For vLLM Server (hosted at localhost:8000)
    python run_generation.py --model /path/to/model --api_base http://localhost:8000/v1 --api_key EMPTY
"""

import os
import json
import glob
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import sys

from experiments.evaluation.cache.manager import CacheManager
from experiments.evaluation.llm.openai_client import OpenAIClient
from xrepotest.config import API_BASE_URL, API_KEY
from xrepotest.languages import SUPPORTED_LANGUAGES
from experiments.evaluation.common.task_ids import normalize_task_id
from experiments.evaluation.common.result_contract import (
    ERROR_STATUS,
    error_result,
    to_response_record,
)


class UnifiedProcessor:
    def __init__(self, api_key=None, base_url=None, delay=0, max_workers=5, max_retries=3, retry_delay=1.0):
        """
        Initialize the UnifiedProcessor.
        """
        if not base_url:
            base_url = API_BASE_URL

        print(f"Initializing client with base_url: {base_url}")
        
        self.client = OpenAIClient(
            api_key=api_key,
            base_url=base_url,
            delay=delay,
            max_retries=max_retries,
            retry_delay=retry_delay
        )
        self.cache_manager = CacheManager()
        self.max_workers = max_workers
    
    def read_prompts_from_jsonl(self, file_path):
        """
        Read prompts from a JSONL file.
        """
        prompts = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    prompt_data = json.loads(line)
                    prompt_data["task_id"] = normalize_task_id(
                        prompt_data.get("task_id", "unknown")
                    )
                    prompts.append(prompt_data)
        return prompts
    
    def process_single_prompt(self, prompt_data, model):
        """
        Process a single prompt and return the result.
        """
        task_id = normalize_task_id(prompt_data.get('task_id', 'unknown'))
        prompt = prompt_data.get('prompt', '')
        system_prompt = prompt_data.get('system_prompt', None)
        
        thread_id = threading.current_thread().name

        result = self.client.generate_result(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
        )

        if result.status == ERROR_STATUS:
            print(f"[{thread_id}] Failed task_id: {task_id} - {result.error or result.response}")

        return to_response_record(task_id=task_id, prompt=prompt, result=result)
    
    def get_output_path(self, input_file, output_file, model_name):
        """Determine output file path based on input structure."""
        if output_file is not None:
            return output_file
            
        # Extract model name and sanitize for filename
        safe_model_name = model_name.replace('/', '_').replace(':', '_')
        
        # Extract language and mode from input path
        # Expected structure: .../responses/language/mode/prompts.jsonl
        path_parts = Path(input_file).parts
        lang = None
        mode = None
        
        for i, part in enumerate(path_parts):
            if part.lower() in SUPPORTED_LANGUAGES:
                lang = part
                # Check if there's a mode after the language
                if i + 1 < len(path_parts):
                    mode = path_parts[i + 1]
                break
        
        # Determine output directory base
        # Output goes back into the same responses tree:
        # responses/rust/standard/prompts.jsonl -> responses/rust/standard/model_name/prompts_responses.jsonl
        
        base_dir = os.path.dirname(input_file)
        
        # Check if we are in a 'mode' directory
        if lang and mode:
            # We are likely in responses/lang/mode
            # Create subdirectory for model
            output_dir = os.path.join(base_dir, safe_model_name)
        elif lang:
            output_dir = os.path.join(base_dir, safe_model_name)
        else:
            # Fallback
            output_dir = os.path.join(base_dir, safe_model_name)
            
        os.makedirs(output_dir, exist_ok=True)
        return os.path.join(output_dir, 'prompts_responses.jsonl')

    def process_file(self, input_file, output_file=None, model="gpt-3.5-turbo", use_multithreading=True):
        """
        Process all prompts in a JSONL file and save responses.
        """
        output_file = self.get_output_path(input_file, output_file, model)
        
        # Check if output file already exists and load existing responses
        existing_responses = self.cache_manager.load_existing_results(output_file)
        
        prompts = self.read_prompts_from_jsonl(input_file)
        
        # Filter out prompts that already have successful responses
        prompts_to_process = self.cache_manager.filter_prompts(prompts, existing_responses)
        
        if len(prompts_to_process) == 0:
            return
        
        print(f"Processing {len(prompts_to_process)} prompts from {input_file}...")
        print(f"Output to: {output_file}")
        
        if use_multithreading:
            # Process prompts concurrently using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all tasks
                future_to_prompt = {
                    executor.submit(self.process_single_prompt, prompt_data, model): prompt_data
                    for prompt_data in prompts_to_process
                }

                # Write results incrementally as they complete
                count = 0
                total = len(prompts_to_process)
                for future in as_completed(future_to_prompt):
                    try:
                        result = future.result()
                        self.cache_manager.append_result(output_file, result)
                        count += 1
                        if count % 10 == 0:
                            print(f"Progress: {count}/{total} ({count/total*100:.1f}%)")
                    except Exception as e:
                        prompt_data = future_to_prompt[future]
                        task_id = normalize_task_id(prompt_data.get('task_id', 'unknown'))
                        print(f"Exception processing task_id {task_id}: {str(e)}")
                        self.cache_manager.append_result(
                            output_file,
                            to_response_record(
                                task_id=task_id,
                                prompt=prompt_data.get('prompt', ''),
                                result=error_result(f"Exception: {str(e)}"),
                            ),
                        )
        else:
            # Process prompts sequentially
            for i, prompt_data in enumerate(prompts_to_process):
                result = self.process_single_prompt(prompt_data, model=model)
                self.cache_manager.append_result(output_file, result)
                if i % 10 == 0:
                    print(f"Progress: {i}/{len(prompts_to_process)}")

        # Deduplicate and sort the output file
        self.cache_manager.deduplicate_file(output_file)
        print(f"\nCompleted! Results saved to {output_file}")
    
    def process_directory(self, directory, model="gpt-3.5-turbo", use_multithreading=True):
        """
        Process all JSONL files in a directory structure.
        """
        jsonl_files = glob.glob(os.path.join(directory, '**', '*prompts.jsonl'), recursive=True)

        if not jsonl_files:
            print("❌ No *prompts.jsonl files found in the input directory. Nothing to process.")
            sys.exit(1)

        print(f"Found {len(jsonl_files)} JSONL files to process.\n")
        
        for i, jsonl_file in enumerate(jsonl_files, 1):
            print(f"\n{'='*80}")
            print(f"File {i}/{len(jsonl_files)}: {jsonl_file}")
            print(f"{'='*80}")
            self.process_file(jsonl_file, model=model, use_multithreading=use_multithreading)


def main():
    """
    Main function with command-line argument support.
    """
    parser = argparse.ArgumentParser(description="Unified Generation Script (OpenAI & vLLM)")
    parser.add_argument("--model", type=str, required=True, help="Model name to use")
    parser.add_argument("--input_dir", type=str, default="../data/responses", help="Input directory containing prompts")
    parser.add_argument("--api_key", type=str, default=None, help="API key (defaults to xrepotest.config.API_KEY)")
    parser.add_argument(
        "--api_base",
        type=str,
        default=API_BASE_URL,
        help=f"API Base URL (default: {API_BASE_URL})",
    )
    parser.add_argument("--max_workers", type=int, default=50, help="Maximum number of concurrent workers")
    parser.add_argument("--delay", type=float, default=0.0, help="Delay between API calls in seconds")
    parser.add_argument("--max_retries", type=int, default=3, help="Maximum number of retry attempts")
    parser.add_argument("--retry_delay", type=float, default=5.0, help="Initial retry delay in seconds")
    parser.add_argument("--no_multithreading", action="store_true", help="Disable multithreading")
    
    args = parser.parse_args()
    
    # Get API key from args or xrepotest.config (file-backed, see API_KEY_FILE)
    # If using local vLLM, user might pass "EMPTY" or we can default to it if api_base is localhost
    api_key = args.api_key or API_KEY

    # If connecting to localhost and no key provided, use dummy key
    if not api_key and "localhost" in args.api_base:
        print("Using dummy API key for localhost...")
        api_key = "EMPTY"

    if not api_key:
        print("Error: API key must be provided via --api_key argument or xrepotest.config.API_KEY_FILE")
        return 1
    
    try:
        # Initialize processor
        processor = UnifiedProcessor(
            api_key=api_key,
            base_url=args.api_base,
            delay=args.delay,
            max_workers=args.max_workers,
            max_retries=args.max_retries,
            retry_delay=args.retry_delay
        )
        
        # Process directory
        processor.process_directory(
            args.input_dir, 
            model=args.model, 
            use_multithreading=not args.no_multithreading
        )
        
        return 0
        
    except ValueError as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
