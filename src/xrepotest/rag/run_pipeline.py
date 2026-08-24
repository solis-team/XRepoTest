"""
Quick start script to run the RAG pipeline.

This script runs the full pipeline on all xrepotest data:
1. Creates code windows from repositories
2. Runs both BM25 and UniXcoder retrieval
3. Saves enriched data with retrieved contexts

Usage:
    python run_pipeline.py
"""

from xrepotest.rag.pipeline import RAGPipeline
from xrepotest.paths import get_rag_enriched_dir, get_repo_data_dir
from xrepotest.rag.config import RAG_DEFAULT_WINDOW_SIZE, RAG_DEFAULT_SLICE_SIZE, RAG_DEFAULT_TOP_K, RAG_WINDOWS_CACHE_DIR


def main():
    """Run the complete RAG pipeline."""
    output_dir = str(get_rag_enriched_dir())
    
    print("="*70)
    print("RAG PIPELINE FOR UNIT TEST GENERATION")
    print("="*70)
    print()
    print("This will:")
    print("  1. Create code windows from all repositories")
    print("  2. Run BM25 retrieval on all xrepotest files")
    print("  3. Run UniXcoder retrieval on all xrepotest files")
    print(f"  4. Save enriched data to {output_dir}/")
    print()
    print("Note: UniXcoder requires GPU for fast processing.")
    print("      This may take several hours on CPU.")
    print()
    
    # Initialize pipeline
    pipeline = RAGPipeline(
        repo_base_dir=str(get_repo_data_dir()),
        windows_dir=RAG_WINDOWS_CACHE_DIR,
        output_dir=output_dir,
        window_size=RAG_DEFAULT_WINDOW_SIZE,      # Lines per window
        slice_size=RAG_DEFAULT_SLICE_SIZE,        # Window overlap
        top_k=RAG_DEFAULT_TOP_K            # Contexts to retrieve
    )
    
    # Step 1: Create windows
    print("\n" + "="*70)
    print("STEP 1: Creating Code Windows")
    print("="*70)
    
    languages = ['go', 'julia', 'php', 'ruby', 'rust']
    pipeline.create_all_repo_windows(languages)
    
    # Step 2: Run retrieval
    print("\n" + "="*70)
    print("STEP 2: Running Retrieval on xrepotest Files")
    print("="*70)
    
    pipeline.process_all_files(
        input_dir="xrepotest_input",
        use_bm25=True,
        use_unixcoder=True
    )
    
    print("\n" + "="*70)
    print("PIPELINE COMPLETE!")
    print("="*70)
    print()
    print(f"Enriched data saved to: {output_dir}/")
    print()
    print("Output files are split by retrieval method:")
    print("  - *_enriched_bm25.jsonl: Original xrepotest data + retrieved_contexts_bm25")
    print("  - *_enriched_unixcoder.jsonl: Original xrepotest data + retrieved_contexts_unixcoder")
    print()


if __name__ == "__main__":
    main()
