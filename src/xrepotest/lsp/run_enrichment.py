"""
Custom script to run LSP enrichment on newly extracted repositories.
"""

import logging
from pathlib import Path
from xrepotest.lsp.lsp_extractor import ArgumentExtractor
from xrepotest.paths import get_project_root, get_lsp_enriched_dir

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_enrichment():
    project_root = get_project_root()
    input_dir = project_root / "data" / "new_extraction"
    repo_base = project_root / "repo_data" / "new_repos"
    
    logger.info(f"Input dir: {input_dir}")
    logger.info(f"Repo base: {repo_base}")
    
    # We use a dummy workspace_root as we will manually override paths in extract_for_language
    # but ArgumentExtractor uses self.workspace_root / config['jsonl_file']
    # So we should probably subclass or monkeypatch if we don't want to change lsp_extractor.py
    # Alternatively, let's just use the extractor and rely on its LANGUAGE_CONFIG
    # but we need it to point to our new extraction.
    
    extractor = ArgumentExtractor(workspace_root=project_root)
    
    # Languages to process
    languages = ['go', 'rust', 'php', 'julia'] # ruby is empty in new_repos
    
    for lang in languages:
        logger.info(f"\n{'='*60}")
        logger.info(f"Enriching {lang.upper()}")
        logger.info("="*60 + "\n")
        
        # Manually configure the paths for this language in the extractor
        extractor.LANGUAGE_CONFIG[lang]['jsonl_file'] = input_dir / f"{lang}_functions.jsonl"
        extractor.LANGUAGE_CONFIG[lang]['repo_base'] = repo_base / lang
        
        # Override the extract_for_language slightly to not join with workspace_root if it's already absolute
        # Actually lsp_extractor.py:
        # jsonl_path = self.workspace_root / config['jsonl_file']
        # repo_base = self.workspace_root / config['repo_base']
        
        # So we set them as relative to project_root
        extractor.LANGUAGE_CONFIG[lang]['jsonl_file'] = (input_dir / f"{lang}_functions.jsonl").relative_to(project_root)
        extractor.LANGUAGE_CONFIG[lang]['repo_base'] = (repo_base / lang).relative_to(project_root)
        
        try:
            extractor.extract_for_language(lang)
        except Exception as e:
            logger.error(f"Failed to process {lang}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    run_enrichment()
