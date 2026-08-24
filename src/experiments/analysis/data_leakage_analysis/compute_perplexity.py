#!/usr/bin/env python3
"""
Compute perplexity scores for test code.
Lower perplexity indicates the model has seen similar code (potential data leakage).
"""

import json
import torch
from pathlib import Path
from typing import List, Dict, Optional
import logging
from tqdm import tqdm

from transformers import AutoModelForCausalLM, AutoTokenizer
from xrepotest.paths import get_project_root, get_data_dir

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PerplexityComputer:
    """Compute perplexity scores for code."""
    
    def __init__(self, model_name: str = "Qwen/Qwen2.5-Coder-7B-Instruct", device: str = "auto"):
        """
        Initialize perplexity computer with Qwen model.
        
        Args:
            model_name: HuggingFace model name
            device: Device to run on ('auto', 'cuda', 'cpu')
        """
        self.model_name = model_name
        logger.info(f"Loading model {model_name}...")
        
        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            trust_remote_code=True,
            padding_side='right'
        )
        
        # Set pad token if not present
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        
        # Load model with appropriate device
        self.device = self._get_device(device)
        logger.info(f"Using device: {self.device}")
        
        if self.device == 'cuda':
            # Load with GPU acceleration
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                trust_remote_code=True,
                torch_dtype=torch.float16,
                device_map="auto"
            )
        else:
            # CPU mode
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                trust_remote_code=True,
                torch_dtype=torch.float32
            )
            self.model.to(self.device)
        
        self.model.eval()
        logger.info("Model loaded successfully")
    
    def _get_device(self, device: str) -> str:
        """Determine the device to use"""
        if device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return device
    
    def compute_perplexity(self, code: str, language: str, max_length: int = 2048) -> Dict:
        """
        Compute perplexity for a code snippet.
        
        Args:
            code: Source code string
            language: Programming language
            max_length: Maximum sequence length
            
        Returns:
            Dictionary with perplexity metrics
        """
        # Add language context prefix
        prompt = f"# Language: {language}\n{code}"
        
        # Tokenize
        try:
            inputs = self.tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=max_length,
                padding=False
            )
            
            # Move to device
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # Compute loss (negative log likelihood)
            with torch.no_grad():
                outputs = self.model(**inputs, labels=inputs["input_ids"])
                loss = outputs.loss
                
                # Perplexity = exp(loss)
                perplexity = torch.exp(loss).item()
                
                # Additional metrics
                num_tokens = inputs["input_ids"].size(1)
                
                return {
                    'perplexity': perplexity,
                    'loss': loss.item(),
                    'num_tokens': num_tokens,
                    'truncated': num_tokens >= max_length,
                    'status': 'ok'
                }
        
        except Exception as e:
            logger.error(f"Error computing perplexity: {e}")
            return {
                'perplexity': None,
                'loss': None,
                'num_tokens': 0,
                'truncated': False,
                'status': 'error',
                'error_message': str(e)
            }
    
    def process_jsonl(self, input_path: Path, output_path: Path):
        """
        Process test JSONL file and compute perplexity scores.
        Saves only summary statistics (not individual function details).
        
        Args:
            input_path: Path to input JSONL file
            output_path: Path to output summary JSON file
        """
        logger.info(f"Processing {input_path}...")
        
        # Load test functions
        test_functions = []
        with open(input_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    test_functions.append(json.loads(line))
        
        logger.info(f"Loaded {len(test_functions)} test functions")
        
        # Compute perplexity for each function
        perplexities = []
        errors = 0
        
        for test_func in tqdm(test_functions, desc="Computing perplexity"):
            ppl_metrics = self.compute_perplexity(
                test_func['test_code'],
                test_func['language']
            )
            
            if ppl_metrics['status'] == 'ok' and ppl_metrics['perplexity'] is not None:
                perplexities.append(ppl_metrics['perplexity'])
            else:
                errors += 1
        
        # Compute summary statistics
        if perplexities:
            perplexities_sorted = sorted(perplexities)
            n = len(perplexities_sorted)
            summary = {
                'model': self.model_name,
                'language': test_functions[0]['language'] if test_functions else 'unknown',
                'total_samples': len(test_functions),
                'successful': len(perplexities),
                'errors': errors,
                'statistics': {
                    'mean': sum(perplexities) / len(perplexities),
                    'median': perplexities_sorted[n // 2],
                    'min': perplexities_sorted[0],
                    'max': perplexities_sorted[-1],
                    'p25': perplexities_sorted[n // 4],
                    'p75': perplexities_sorted[(3 * n) // 4]
                }
            }
        else:
            summary = {
                'model': self.model_name,
                'language': test_functions[0]['language'] if test_functions else 'unknown',
                'total_samples': len(test_functions),
                'successful': 0,
                'errors': errors,
                'statistics': {}
            }
        
        # Save summary only
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved summary to {output_path}")
        
        # Print summary statistics
        if perplexities:
            logger.info(f"Perplexity statistics:")
            logger.info(f"  Mean: {summary['statistics']['mean']:.2f}")
            logger.info(f"  Min: {summary['statistics']['min']:.2f}")
            logger.info(f"  Max: {summary['statistics']['max']:.2f}")
            logger.info(f"  Median: {summary['statistics']['median']:.2f}")
    
    def process_mceval_dataset(self, output_path: Path, split: str = 'test'):
        """
        Process McEval generation dataset and compute perplexity on test fields.
        
        Args:
            output_path: Path to save results
            split: Dataset split to process ('test', 'train', 'validation')
        """
        from datasets import load_dataset
        
        logger.info(f"Loading McEval generation dataset (split: {split})...")
        ds = load_dataset("Multilingual-Multimodal-NLP/McEval", "generation")
        dataset = ds[split]
        
        logger.info(f"Loaded {len(dataset)} samples from McEval")
        
        # Process each sample
        perplexities_all = []
        perplexities_by_lang = {}
        skipped = 0
        errors = 0
        
        for idx, sample in enumerate(tqdm(dataset, desc="Computing perplexity on McEval")):
            # Extract test field
            test_code = sample.get('test', '')
            language = sample.get('language', 'unknown')
            
            # Skip empty tests
            if not test_code or not test_code.strip():
                skipped += 1
                continue
            
            # Compute perplexity
            ppl_metrics = self.compute_perplexity(test_code, language)
            
            if ppl_metrics['status'] == 'ok' and ppl_metrics['perplexity'] is not None:
                ppl = ppl_metrics['perplexity']
                perplexities_all.append(ppl)
                if language not in perplexities_by_lang:
                    perplexities_by_lang[language] = []
                perplexities_by_lang[language].append(ppl)
            else:
                errors += 1
        
        # Compute summary statistics
        summary = {
            'model': self.model_name,
            'dataset': 'McEval_generation',
            'split': split,
            'total_samples': len(dataset),
            'skipped_empty': skipped,
            'successful': len(perplexities_all),
            'errors': errors
        }
        
        # Overall statistics
        if perplexities_all:
            ppls_sorted = sorted(perplexities_all)
            n = len(ppls_sorted)
            summary['overall_statistics'] = {
                'mean': sum(ppls_sorted) / n,
                'median': ppls_sorted[n // 2],
                'min': ppls_sorted[0],
                'max': ppls_sorted[-1],
                'p25': ppls_sorted[n // 4],
                'p75': ppls_sorted[(3 * n) // 4]
            }
        
        # Per-language statistics
        if perplexities_by_lang:
            summary['per_language'] = {}
            for lang, ppls in perplexities_by_lang.items():
                ppls_sorted = sorted(ppls)
                n = len(ppls_sorted)
                summary['per_language'][lang] = {
                    'count': n,
                    'mean': sum(ppls_sorted) / n,
                    'median': ppls_sorted[n // 2],
                    'min': ppls_sorted[0],
                    'max': ppls_sorted[-1]
                }
        
        # Save summary only
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved summary to {output_path}")
        logger.info(f"Processed {len(perplexities_all)} samples, skipped {skipped} empty tests, {errors} errors")
        
        # Print summary statistics
        if perplexities_all:
            logger.info(f"\nMcEval Overall Perplexity statistics:")
            stats = summary['overall_statistics']
            logger.info(f"  Mean: {stats['mean']:.2f}")
            logger.info(f"  Min: {stats['min']:.2f}")
            logger.info(f"  Max: {stats['max']:.2f}")
            logger.info(f"  Median: {stats['median']:.2f}")
            
            logger.info(f"\nPer-language statistics:")
            for lang, lang_stats in sorted(summary['per_language'].items()):
                logger.info(f"  {lang}: mean={lang_stats['mean']:.2f}, "
                           f"median={lang_stats['median']:.2f}, "
                           f"count={lang_stats['count']}")
    
    def process_humaneval_dataset(self, output_path: Path, split: str = 'test'):
        """
        Process HumanEval dataset and compute perplexity on test fields.
        
        Args:
            output_path: Path to save results
            split: Dataset split to process ('test', 'train', 'validation')
        """
        from datasets import load_dataset
        
        logger.info(f"Loading HumanEval dataset (split: {split})...")
        ds = load_dataset("openai/openai_humaneval")
        dataset = ds[split]
        
        logger.info(f"Loaded {len(dataset)} samples from HumanEval")
        
        # Process each sample
        perplexities_all = []
        skipped = 0
        errors = 0
        
        for idx, sample in enumerate(tqdm(dataset, desc="Computing perplexity on HumanEval")):
            # Extract test field
            test_code = sample.get('test', '')
            
            # Skip empty tests
            if not test_code or not test_code.strip():
                skipped += 1
                continue
            
            # Remove METADATA section if present
            # Pattern: METADATA = {...}
            import re
            test_code = re.sub(r'METADATA\s*=\s*\{[^}]*\}\s*\n*', '', test_code, flags=re.DOTALL)
            test_code = test_code.strip()
            
            if not test_code:
                skipped += 1
                continue
            
            # Compute perplexity (HumanEval is Python only)
            ppl_metrics = self.compute_perplexity(test_code, 'python')
            
            if ppl_metrics['status'] == 'ok' and ppl_metrics['perplexity'] is not None:
                perplexities_all.append(ppl_metrics['perplexity'])
            else:
                errors += 1
        
        # Compute summary statistics
        summary = {
            'model': self.model_name,
            'dataset': 'HumanEval',
            'split': split,
            'total_samples': len(dataset),
            'skipped_empty': skipped,
            'successful': len(perplexities_all),
            'errors': errors
        }
        
        # Overall statistics
        if perplexities_all:
            ppls_sorted = sorted(perplexities_all)
            n = len(ppls_sorted)
            summary['statistics'] = {
                'mean': sum(ppls_sorted) / n,
                'median': ppls_sorted[n // 2],
                'min': ppls_sorted[0],
                'max': ppls_sorted[-1],
                'p25': ppls_sorted[n // 4],
                'p75': ppls_sorted[(3 * n) // 4]
            }
        
        # Save summary only
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved summary to {output_path}")
        logger.info(f"Processed {len(perplexities_all)} samples, skipped {skipped} empty tests, {errors} errors")
        
        # Print summary statistics
        if perplexities_all:
            logger.info(f"\nHumanEval Perplexity statistics:")
            stats = summary['statistics']
            logger.info(f"  Mean: {stats['mean']:.2f}")
            logger.info(f"  Min: {stats['min']:.2f}")
            logger.info(f"  Max: {stats['max']:.2f}")
            logger.info(f"  Median: {stats['median']:.2f}")
    
    def process_testgeneval_dataset(self, output_path: Path, split: str = 'test', test_dir: Optional[Path] = None):
        """
        Process TestGenEval dataset and compute perplexity on test file contents.
        
        TestGenEval is a Python-only dataset containing test patches from GitHub repos.
        This method loads test code from local JSONL files extracted by extract_testgeneval.py.
        
        Args:
            output_path: Path to save results
            split: Dataset split to process ('test', 'train', 'validation')
            test_dir: Optional custom directory containing test files (auto-detect if None)
        """
        # TestGenEval test files should be extracted first using extract_testgeneval.py
        # Look for files in test_samples_testgeneval_/ directory
        if test_dir is None:
            test_dir = get_testgeneval_dir(split)
            if not test_dir.exists():
                # Fallback to legacy name
                test_dir = get_data_dir() / 'test_samples_testgeneval'
        else:
            test_dir = Path(test_dir)
        
        if not test_dir.exists():
            logger.error(f"TestGenEval test directory not found: {test_dir}")
            logger.error("Run extract_testgeneval.py first to extract tests from GitHub")
            return
        
        logger.info(f"Loading TestGenEval tests from {test_dir}...")
        logger.info(f"ℹ️  Note: TestGenEval is Python-only")
        
        # TestGenEval is Python-only
        perplexities_all = []
        skipped = 0
        errors = 0
        total_samples = 0
        
        # Look for python_tests.jsonl file
        test_file = test_dir / 'python_tests.jsonl'
        if not test_file.exists():
            logger.error(f"Python test file not found: {test_file}")
            logger.error("Run extract_testgeneval.py first to extract tests from GitHub")
            return
        
        logger.info(f"Processing Python tests from {test_file.name}...")
        
        # Load samples
        samples = []
        with open(test_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        
        total_samples = len(samples)
        logger.info(f"  Loaded {total_samples} Python test samples")
        
        # Process each sample
        for sample in tqdm(samples, desc="Computing perplexity for Python tests"):
            test_code = sample.get('test_code', '')
            # TestGenEval is Python-only (no language field needed)
            language = sample.get('language', 'python')
            
            # Skip empty tests
            if not test_code or not test_code.strip():
                skipped += 1
                continue
            
            # Compute perplexity
            ppl_metrics = self.compute_perplexity(test_code, language)
            
            if ppl_metrics['status'] == 'ok' and ppl_metrics['perplexity'] is not None:
                perplexities_all.append(ppl_metrics['perplexity'])
            else:
                errors += 1
        
        # Compute summary statistics
        summary = {
            'model': self.model_name,
            'dataset': 'TestGenEval',
            'split': split,
            'language': 'python',  # TestGenEval is Python-only
            'total_samples': total_samples,
            'skipped_empty': skipped,
            'successful': len(perplexities_all),
            'errors': errors
        }
        
        # Statistics (Python-only, so no per-language breakdown needed)
        if perplexities_all:
            ppls_sorted = sorted(perplexities_all)
            n = len(ppls_sorted)
            summary['statistics'] = {
                'mean': sum(ppls_sorted) / n,
                'median': ppls_sorted[n // 2],
                'min': ppls_sorted[0],
                'max': ppls_sorted[-1],
                'p25': ppls_sorted[n // 4],
                'p75': ppls_sorted[(3 * n) // 4]
            }
        
        # Save summary only
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved summary to {output_path}")
        logger.info(f"Processed {len(perplexities_all)} samples, skipped {skipped} empty tests, {errors} errors")
        
        # Print summary statistics
        if perplexities_all:
            logger.info(f"\nTestGenEval Perplexity statistics (Python):")
            stats = summary['statistics']
            logger.info(f"  Mean: {stats['mean']:.2f}")
            logger.info(f"  Min: {stats['min']:.2f}")
            logger.info(f"  Max: {stats['max']:.2f}")
            logger.info(f"  Median: {stats['median']:.2f}")


def get_output_dir() -> Path:
    """Get the output directory for test analysis results."""
    return get_data_dir() / 'test_analysis'

def get_test_samples_dir() -> Path:
    """Get the directory containing test samples."""
    return get_data_dir() / 'test_samples'

def get_testgeneval_dir(split: str = 'test') -> Path:
    """Get the TestGenEval test directory for a given split."""
    return get_data_dir() / f'test_samples_testgeneval_{split}'


def main():
    """Main entry point for compute_perplexity CLI."""
    import argparse
    parser = argparse.ArgumentParser(description='Compute perplexity scores for test code')
    parser.add_argument('--input', type=Path,
                        help='Input JSONL file with test functions')
    parser.add_argument('--output', type=Path,
                        help='Output JSONL file with perplexity scores')
    parser.add_argument('--model', type=str, default='Qwen/Qwen2.5-Coder-7B-Instruct',
                        help='HuggingFace model name')
    parser.add_argument('--device', type=str, default='auto',
                        choices=['auto', 'cuda', 'cpu'],
                        help='Device to run on')
    parser.add_argument('--batch', action='store_true',
                        help='Process all languages in test_samples/ directory')
    parser.add_argument('--mceval', action='store_true',
                        help='Process McEval generation dataset test fields')
    parser.add_argument('--mceval-split', type=str, default='test',
                        choices=['test', 'train', 'validation'],
                        help='McEval dataset split to process')
    parser.add_argument('--humaneval', action='store_true',
                        help='Process HumanEval dataset test fields')
    parser.add_argument('--humaneval-split', type=str, default='test',
                        choices=['test', 'train', 'validation'],
                        help='HumanEval dataset split to process')
    parser.add_argument('--testgeneval', action='store_true',
                        help='Process TestGenEval dataset test fields (requires extract_testgeneval.py first)')
    parser.add_argument('--testgeneval-split', type=str, default='test',
                        choices=['test', 'train', 'validation'],
                        help='TestGenEval dataset split to process')
    parser.add_argument('--testgeneval-dir', type=str, default=None,
                        help='TestGenEval test directory (default: auto-detect from split)')

    args = parser.parse_args()

    # Initialize perplexity computer
    computer = PerplexityComputer(model_name=args.model, device=args.device)

    # Extract short model name for filename
    model_short = args.model.split('/')[-1].replace('-', '_').lower()

    if args.mceval:
        # Process McEval generation dataset
        output_file = get_output_dir() / f'mceval_{args.mceval_split}_{model_short}_summary.json'
        computer.process_mceval_dataset(output_file, split=args.mceval_split)
    elif args.humaneval:
        # Process HumanEval dataset
        output_file = get_output_dir() / f'humaneval_{args.humaneval_split}_{model_short}_summary.json'
        computer.process_humaneval_dataset(output_file, split=args.humaneval_split)
    elif args.testgeneval:
        # Process TestGenEval dataset
        output_file = get_output_dir() / f'testgeneval_{args.testgeneval_split}_{model_short}_summary.json'
        test_dir = Path(args.testgeneval_dir) if args.testgeneval_dir else None
        computer.process_testgeneval_dataset(output_file, split=args.testgeneval_split, test_dir=test_dir)
    elif args.batch:
        # Process all language files in test_samples/
        test_dir = get_test_samples_dir()
        if not test_dir.exists():
            logger.error(f"Directory {test_dir} not found")
            return

        output_dir = get_output_dir()
        for lang in ['go', 'rust', 'ruby', 'php', 'julia']:
            input_file = test_dir / f"{lang}_tests.jsonl"
            if input_file.exists():
                output_file = output_dir / f"{lang}_{model_short}_summary.json"
                computer.process_jsonl(input_file, output_file)
            else:
                logger.warning(f"Input file not found: {input_file}")
    else:
        # Process single file
        if not args.input or not args.output:
            parser.error("--input and --output are required when not using --batch mode")
        computer.process_jsonl(args.input, args.output)


if __name__ == '__main__':
    main()
