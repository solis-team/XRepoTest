"""
Prompt Creation Module

Create prompts for all supported prompt modes:
  - standard
  - lsp_context
  - file_context
  - rag_bm25
  - rag_dense

The CLI is mode-driven via --mode.

Output: Saves prompts to ../data/responses/{lang}/{mode}/ directory.
"""
import argparse
import hashlib
import json
import os
import sys
import textwrap
from datasets import load_dataset
from experiments.evaluation.generation.prompts.tree_sitter_utils import (
    delete_test_from_filecontext,
    rust_parser,
    go_parser,
    julia_parser,
)
from experiments.evaluation.generation.prompts.constants import (
    DEFAULT_RAG_SLICE_SIZE,
    DEFAULT_RAG_TOP_K,
    datapath,
    bm_25_rag_datapath,
    dense_rag_datapath,
    lsp_datapath,
    get_rag_datapath,
)
from experiments.evaluation.generation.prompts.template import SYSTEM_PROMPTS, get_template
from experiments.evaluation.common.modes import (
    LSP_DATA_MODE,
    RAG_MODES,
    PROMPT_MODE_CHOICES as MODE_CHOICES,
)
import re


lang_parsers = {
    "rust": rust_parser,
    "go": go_parser,
    "julia": julia_parser
}


class PromptCreator:
    """Creates and saves prompts for test generation."""
    
    def __init__(
        self,
        task_name,
        data_path,
        split="train",
        system_prompt=None,
        template=None,
        lsp_context=False,
        is_rag=False,
        file_context=False,
        top_k=None,
    ):
        """
        Initialize PromptCreator.
        
        Args:
            task_name: Language task name (rust, go, julia, ruby, php)
            data_path: Dataset path configuration
            split: Dataset split
            system_prompt: System prompt for API models
            template: Prompt template
            lsp_context: Include LSP context (argument definitions + symbol definitions)
            is_rag: Using RAG context
            file_context: Include file context
        """
        self.task_name = task_name
        self.template = template
        self.lsp_context = lsp_context
        self.is_rag = is_rag
        self.file_context = file_context
        self.system_prompt = system_prompt
        self.top_k = top_k  # Number of RAG contexts to include (None = all)
        self.context_key = data_path.get("context_key")  # For RAG mode

        # Build task_id lookup for LSP context when LSP data is a subset (e.g., only new repos)
        self.lsp_lookup = {}
        if self.lsp_context:
            from experiments.evaluation.generation.prompts.constants import lsp_datapath
            lsp_path = lsp_datapath[self.task_name]
            lsp_records = self._load_jsonl(lsp_path["file"])
            self.lsp_lookup = {record["task_id"]: record for record in lsp_records}
            print(f"Built LSP lookup with {len(self.lsp_lookup)} records")

        # Build task_id lookup for RAG context when RAG data is a subset
        self.rag_lookup = {}
        if self.is_rag:
            from experiments.evaluation.generation.prompts.constants import bm_25_rag_datapath, dense_rag_datapath
            # Determine which RAG type by context_key
            if self.context_key == "retrieved_contexts_bm25":
                rag_path = bm_25_rag_datapath[self.task_name]
            else:
                rag_path = dense_rag_datapath[self.task_name]
            rag_records = self._load_jsonl(rag_path["file"])
            self.rag_lookup = {record["task_id"]: record for record in rag_records}
            print(f"Built RAG lookup with {len(self.rag_lookup)} records")

        # Load dataset from HuggingFace or local file
        # NOTE: trust_remote_code is intentionally NOT used — we only load plain
        # JSONL data repos, never remote custom loading scripts. Never re-add it
        # for an arbitrary repo id (it executes repo-supplied code).
        if data_path.get("file"):
            # Load from local JSONL file (for RAG mode)
            self.dataset = self._load_jsonl(data_path["file"])
        elif data_path.get("split"):
            self.dataset = load_dataset(data_path["repo"], split=data_path["split"]).to_list()
        else:
            self.dataset = load_dataset(data_path["repo"], split=split).to_list()

        print(f"Loaded dataset with {len(self.dataset)} examples")
    
    def _load_jsonl(self, file_path):
        """Load data from JSONL file."""
        data = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                data.append(json.loads(line))
        return data
    
    def _build_standard_prompt(self, example):
        """Build standard prompt from language-specific template."""
        # Prepare code with class signature if needed
        metadata = example.get("metadata", {})
        class_signature = metadata.get("class_signature", "") if metadata else ""
        
        if class_signature:
            code = "{} {{\n{}\n}}".format(
                class_signature, 
                textwrap.indent(text=example["focal_code"], prefix='    ')
            )
        else:
            code = example["focal_code"]
        
        # Get the appropriate template (language-specific or generic)
        template = get_template(self.task_name)
        
        # Build template variables
        template_vars = {
            "language": self.task_name,
            "function_code": code,
            "file_path": example.get("file_path", ""),
            "function_name": example.get("function_name", "")
        }
        
        # Add language-specific metadata from dataset if available
        if self.task_name.lower() == "go" and metadata:
            template_vars["package_name"] = metadata.get("package", "main")
            func_name = template_vars["function_name"]
            if func_name:
                template_vars["function_name"] = func_name[0].upper() + func_name[1:]
        
        # Add PHP-specific metadata from dataset if available
        if self.task_name.lower() == "php" and metadata:
            template_vars["namespace"] = metadata.get("namespace", "App")
        
        # Format the prompt with available variables
        try:
            main_prompt = template.format(**template_vars)
        except KeyError as e:
            # Fallback to basic format if some variables are missing
            print(f"Warning: Missing template variable {e}, using basic format")
            from experiments.evaluation.generation.prompts.template import TEMPLATE
            main_prompt = TEMPLATE.format(
                language=self.task_name,
                function_code=code
            )
        
        return code, main_prompt
    
    def _add_context_to_prompt(self, example, prompt, file_content=None):
        """Add various contexts to the prompt.
        
        Args:
            example: The example data
            prompt: The prompt to add context to
            file_content: Optional pre-processed file content (to avoid duplicate processing)
        """
        # Add RAG context
        if self.is_rag:
            # Check if context_key is specified (for enriched files)
            if self.context_key and self.context_key in example:
                contexts = example[self.context_key]
                if contexts:
                    # Filter contexts by top_k if specified
                    if self.top_k is not None:
                        contexts = contexts[:self.top_k]
                    # Format RAG contexts - each context has 'context' key with the actual code
                    context_text = "\n\n".join([
                        f"Example {i+1}:\n{ctx.get('context', ctx.get('focal_code', str(ctx)))}"
                        for i, ctx in enumerate(contexts)
                    ])
                    prompt = "#RELEVANT CONTEXT\n" + context_text + "\n#END_OF_CONTEXT\n\n" + prompt
            # Fallback to legacy "context" field
            elif "context" in example:
                prompt = "#RELEVANT CONTEXT\n" + example["context"] + "\n#END_OF_CONTEXT\n\n" + prompt
        
        # Add file context
        elif self.file_context:
            # file_content should already be prepared by caller
            prompt = "\n#CURRENT FILE: {}\n{}\n#ENDFILE\n".format(
                example["file_path"], 
                file_content
            ) + prompt
        
        return prompt
    
    def _add_lsp_context(self, example, prompt, file_content=None):
        """Add LSP context (argument definitions, callee definitions, and references) to the prompt.
        
        Args:
            example: The example data
            prompt: The prompt to add context to
            file_content: Optional file content to check against (for filtering duplicate definitions)
        """
        function_component = example.get("function_component", {})

        # 1) Argument type definitions (existing behavior)
        arg_defs = function_component.get("argument_definitions_lsp")
        argument_definitions = []
        if arg_defs:
            for arg in arg_defs:
                for def_item in arg.get("definitions", []) or []:
                    definition_text = def_item.get("definition")
                    if definition_text:
                        # If file_content is provided, only add if not already in file
                        if file_content is None or definition_text.strip() not in file_content:
                            argument_definitions.append(definition_text)

        argument_block = ""
        if argument_definitions:
            pre_prompt = "\n".join([d for d in argument_definitions]).strip()
            argument_block = "#ARGUMENT_DEFINITIONS\n" + pre_prompt + "\n#END_OF_DEFINITIONS\n"

        # 2) Symbol definitions extracted from LSP token analysis (new format)
        tokens = (
            function_component.get("focal_method_analysis", {})
            .get("tokens", [])
        )

        callee_definitions = []  # Definitions của các callee
        callee_references = []   # References (usage examples) của các callee

        seen_def_sigs = set()
        seen_ref_sigs = set()

        for token in tokens or []:
            # Lấy DEFINITIONS
            if token.get("need_definition"):
                def_code = ((token.get("definition") or {}).get("code"))
                if def_code and def_code.strip():
                    cleaned = def_code.strip()
                    
                    func_pattern = r'func\s+(\w+)\s*\([^)]*\)\s*(?:\([^)]*\))?\s*(?:\w+)?'
                    funcs_in_code = re.findall(func_pattern, cleaned)
                    
                    normalized = ' '.join(cleaned.split())
                    code_sig = hashlib.md5(normalized.encode()).hexdigest()
                    func_sig = tuple(sorted(set(funcs_in_code))) if funcs_in_code else ('_no_func_',)
                    combined_sig = (code_sig, func_sig)
                    
                    if combined_sig not in seen_def_sigs and cleaned.strip():
                        seen_def_sigs.add(combined_sig)
                        callee_definitions.append(cleaned)
            
            # Lấy REFERENCES
            if token.get("need_references"):
                refs = token.get("references", [])
                for ref in refs or []:
                    ref_code = ref.get("code")
                    if ref_code and ref_code.strip():
                        cleaned_ref = ref_code.strip()
                        
                        normalized_ref = ' '.join(cleaned_ref.split())
                        ref_sig = hashlib.md5(normalized_ref.encode()).hexdigest()
                        
                        if ref_sig not in seen_ref_sigs and cleaned_ref.strip():
                            seen_ref_sigs.add(ref_sig)
                            callee_references.append(cleaned_ref)

        # Tạo 2 blocks riêng biệt
        definitions_block = ""
        if callee_definitions:
            def_text = "\n\n".join(callee_definitions).strip()
            if def_text:
                definitions_block = "#CALLEE_DEFINITIONS\n" + def_text + "\n#END_CALLEE_DEFINITIONS\n"

        references_block = ""
        if callee_references:
            ref_text = "\n\n".join(callee_references).strip()
            if ref_text:
                references_block = "#CONDITION_REFERENCES\n" + ref_text + "\n#END_CONDITION_REFERENCES\n"

        # Kết hợp vào LSP context
        if argument_block or definitions_block or references_block:
            lsp_block = "#LSP_CONTEXT\n" + argument_block + definitions_block + references_block + "#END_LSP_CONTEXT\n\n"
            prompt = lsp_block + prompt
        
        return prompt
    
    def create_prompts(self):
        """Create prompts for all examples in the dataset."""
        processed_examples = []

        for example in self.dataset:
            task_id = example.get("task_id")
            # Look up LSP record by task_id if available, otherwise use example
            lsp_record = self.lsp_lookup.get(task_id, example) if self.lsp_lookup else example
            # Look up RAG record by task_id if available, otherwise use example
            rag_record = self.rag_lookup.get(task_id, example) if self.rag_lookup else example

            # Standard prompt construction
            code, main_prompt = self._build_standard_prompt(example)
            
            # Prepare file content once (if needed for file_context mode)
            file_content = None
            if self.file_context:
                if self.task_name.lower() == "rust":
                    file_content = delete_test_from_filecontext(
                        lang_parsers[self.task_name.lower()], 
                        example["file_content"]
                    )
                else:
                    file_content = example.get("file_content", "")
            
            # Add LSP context if needed.
            # Pass file_content for filtering duplicate definitions
            if self.lsp_context:
                main_prompt = self._add_lsp_context(lsp_record, main_prompt, file_content)
            
            # Add other contexts if needed (RAG/file_context)
            # Pass file_content to avoid re-processing
            main_prompt = self._add_context_to_prompt(rag_record, main_prompt, file_content)
            
            example['system_prompt'] = self.system_prompt if self.system_prompt else ""
            example['prompt'] = main_prompt
            # task_id should already be present from data, but ensure it's set
            if example.get('task_id') is None:
                example['task_id'] = task_id
            processed_examples.append(example)
        
        return processed_examples
    
    def save_prompts(self, prompts, output_dir):
        """Save prompts to JSONL file."""
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "prompts.jsonl")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for prompt_data in prompts:
                # Save system_prompt and prompt as separate fields
                minimal_data = {
                    'task_id': prompt_data['task_id'],
                    'system_prompt': prompt_data.get('system_prompt', ''),
                    'prompt': prompt_data['prompt']
                }
                f.write(json.dumps(minimal_data) + "\n")
        
        print(f"✓ Saved {len(prompts)} prompts to: {output_file}")
        return output_file


def main():
    parser = argparse.ArgumentParser(description="Create and save prompts for API-based test generation")
    parser.add_argument("--split", type=str, required=True, help="Dataset split")
    parser.add_argument(
        "--lang",
        type=lambda value: value.strip().lower(),
        choices=sorted(datapath.keys()),
        default="rust",
        help="Programming language",
    )
    parser.add_argument("--output_dir", type=str, required=True, help="Output directory for prompts")

    parser.add_argument(
        "--mode",
        type=str,
        choices=MODE_CHOICES,
        default=None,
        help=(
            "Prompt mode. "
            "Options: standard, lsp_context, file_context, rag_bm25, rag_dense."
        ),
    )

    # RAG mode tuning
    parser.add_argument('--context_size', type=int, choices=[30, 50, 70], default=None,
                       help="Context window size for RAG modes")
    parser.add_argument('--top_k', type=int, default=None,
                       help="Number of top RAG contexts to include (default: all contexts from file)")

    opt = parser.parse_args()
    mode = opt.mode if opt.mode is not None else "standard"
    rag_type = "bm25" if mode == "rag_bm25" else "dense" if mode == "rag_dense" else None

    if rag_type is None and (opt.context_size is not None or opt.top_k is not None):
        parser.error("--context_size and --top_k are only valid for rag_bm25 or rag_dense modes")

    # Use language-specific system prompt from template.py
    system_prompt = SYSTEM_PROMPTS.get(opt.lang, 
        "You are a helpful coding assistant. Your task is to generate unittest for a given function.")

    # Use language-specific template from template.py
    template = get_template(opt.lang)
    print(f"Using template for {opt.lang}")
    print(f"Using mode: {mode}")

    # Determine data path
    if mode == LSP_DATA_MODE:
        # Use configured xrepotest-produced LSP data path
        data_path = lsp_datapath[opt.lang]
        print(f"Using LSP data with context from {data_path['file']}")
    elif mode in RAG_MODES:
        # Use configured xrepotest-produced RAG data path
        # If context_size is specified, use parameterized file path
        if opt.context_size:
            data_path = get_rag_datapath(
                language=opt.lang,
                context_size=opt.context_size,
                step_size=DEFAULT_RAG_SLICE_SIZE,
                top_k=DEFAULT_RAG_TOP_K,
                rag_type=rag_type
            )
            print(f"Using RAG data: {rag_type.upper()} from {data_path['file']} (ws={opt.context_size}, filtering to top_k={opt.top_k or 'all'})")
        else:
            # Fallback to default paths (backward compatibility)
            if rag_type == "bm25":
                data_path = bm_25_rag_datapath[opt.lang]
                print(f"Using RAG data: BM25 (sparse) from {data_path['file']}")
            else:
                data_path = dense_rag_datapath[opt.lang]
                print(f"Using RAG data: Dense (unixcoder) from {data_path['file']}")
    else:
        # Use configured xrepotest-produced standard data path
        data_path = datapath[opt.lang]
        if "file" in data_path:
            print(f"Using local standard dataset from {data_path['file']}")
        else:
            print(f"Using standard HuggingFace dataset: {data_path['repo']} (split: {data_path['split']})")
    
    # Initialize prompt creator
    try:
        creator = PromptCreator(
            task_name=opt.lang,
            data_path=data_path,
            split=opt.split,
            system_prompt=system_prompt,
            template=template,
            lsp_context=mode == "lsp_context",
            is_rag=mode in RAG_MODES,
            file_context=mode == "file_context",
            top_k=opt.top_k,
        )
    except FileNotFoundError:
        print(
            "\n❌ Prompt dataset not found. The benchmark data is not present locally.\n"
            "   Run `python scripts/fetch_data.py` to download it from the HuggingFace Hub "
            "(see the README's 'Benchmark data' section).\n",
            file=sys.stderr,
        )
        sys.exit(1)

    # Create prompts
    print("\nCreating prompts...")
    print("=" * 80)
    prompts_data = creator.create_prompts()
    
    # Print sample
    print("\n" + "=" * 25 + " Sample Prompt " + "=" * 25)
    sample_idx = min(50, len(prompts_data) - 1)
    print(prompts_data[sample_idx]['prompt'])
    print(f"\nTotal prompts: {len(prompts_data)}")
    print("=" * 63)
    
    # Save prompts
    print("\nSaving prompts...")
    creator.save_prompts(prompts_data, opt.output_dir)
    
    print("\n" + "=" * 80)
    print("✓ Prompt creation completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()
