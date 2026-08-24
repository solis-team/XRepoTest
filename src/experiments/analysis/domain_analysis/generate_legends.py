"""
Generate separate legend files for spider charts
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path

# Configuration
SCRIPT_DIR = Path(__file__).parent

# Model definitions for standard mode (14 models)
STANDARD_MODELS = {
    "accounts_fireworks_models_deepseek-v3p2": "DeepSeek V3.2",
    "accounts_fireworks_models_deepseek-v4-pro": "DeepSeek V4 Pro",
    "accounts_fireworks_models_glm-5": "GLM-5",
    "accounts_fireworks_models_gpt-oss-120b": "GPT-OSS 120B",
    "accounts_fireworks_models_kimi-k2p5": "Kimi K2 Pro",
    "accounts_fireworks_models_llama-v3p3-70b-instruct": "Llama 3.3 70B",
    "accounts_fireworks_models_minimax-m2p7": "Minimax 2.7",
    "accounts_fireworks_models_qwen3-8b": "Qwen3 8B",
    "claude-haiku-4.5": "Claude 4.5 Haiku",
    "claude-sonnet-4-5": "Claude 4.5 Sonnet",
    "mistralai_Codestral-22B-v0.1": "Codestral 22B",
    "gpt-5.2": "GPT-5.2",
    "qwen3-coder-next": "Qwen3 Coder Next",
    "01-ai_Yi-Coder-9B-Chat": "Yi-Coder 9B",
}

# Model definitions for file context mode (6 models)
FILE_CONTEXT_MODELS = {
    "accounts_fireworks_models_gpt-oss-120b": "GPT-OSS 120B",
    "claude-sonnet-4-5": "Claude 4.5 Sonnet",
    "mistralai_Codestral-22B-v0.1": "Codestral 22B",
    "gpt-5.2": "GPT-5.2",
    "qwen3-coder-next": "Qwen3 Coder Next",
    "01-ai_Yi-Coder-9B-Chat": "Yi-Coder 9B",
}

# Colors and styles for 14 models (standard mode)
STANDARD_COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
    '#3aadd9', '#f5c243', '#45a54a', '#d94436'
]

# Colors and styles for 6 models (file context mode)
FILE_CONTEXT_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']


def create_legend_standard():
    """Create legend for standard mode (10 models)"""
    output_dir = SCRIPT_DIR / "spider_charts"
    output_dir.mkdir(exist_ok=True)
    
    fig, ax = plt.subplots(figsize=(18, 4))
    ax.axis('off')
    
    # Create legend handles
    handles = []
    labels = []
    
    for idx, (model_id, model_name) in enumerate(STANDARD_MODELS.items()):
        handle = mpatches.Patch(
            color=STANDARD_COLORS[idx],
            label=model_name
        )
        handles.append(handle)
        labels.append(model_name)
    
    # Create legend
    ax.legend(handles, labels, loc='center', fontsize=14,
                      framealpha=0.95, ncol=7, columnspacing=1.5,
                      handlelength=2, handleheight=1.5)
    
    # Save figure
    output_file = output_dir / "legend_standard.pdf"
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✓ Saved: {output_file}")
    
    output_file_png = output_dir / "legend_standard.png"
    plt.savefig(output_file_png, dpi=300, bbox_inches='tight')
    print(f"✓ Saved: {output_file_png}")
    
    plt.close()


def create_legend_file_context():
    """Create legend for file context mode (3 models)"""
    output_dir = SCRIPT_DIR / "spider_charts"
    output_dir.mkdir(exist_ok=True)
    
    fig, ax = plt.subplots(figsize=(10, 2))
    ax.axis('off')
    
    # Create legend handles
    handles = []
    labels = []
    
    for idx, (model_id, model_name) in enumerate(FILE_CONTEXT_MODELS.items()):
        handle = mpatches.Patch(
            color=FILE_CONTEXT_COLORS[idx],
            label=model_name
        )
        handles.append(handle)
        labels.append(model_name)
    
    # Create legend
    ax.legend(handles, labels, loc='center', fontsize=16,
                      framealpha=0.95, ncol=3, columnspacing=2.0,
                      handlelength=2, handleheight=1.5)
    
    # Save figure
    output_file = output_dir / "legend_file_context.pdf"
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✓ Saved: {output_file}")
    
    output_file_png = output_dir / "legend_file_context.png"
    plt.savefig(output_file_png, dpi=300, bbox_inches='tight')
    print(f"✓ Saved: {output_file_png}")
    
    plt.close()


def main():
    """Generate all legends"""
    print("="*70)
    print("GENERATING LEGEND FILES")
    print("="*70)
    
    print("\nGenerating standard mode legend...")
    create_legend_standard()
    
    print("\nGenerating file context mode legend...")
    create_legend_file_context()
    
    print("\n" + "="*70)
    print("GENERATION COMPLETE")
    print("="*70)


if __name__ == "__main__":
    main()
