"""
Plotting functions for correlation analysis.

Generates heatmaps, scatter plots, and legends for Tessera metrics vs SWE-bench.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import r2_score

# Output directory
OUTPUT_DIR = Path(__file__).parent

# Default style settings
SNS_STYLE = "whitegrid"
SNS_CONTEXT = "talk"


def plot_correlation_heatmap(corr_matrix: pd.DataFrame, save_name: str = "correlation_heatmap_all_models.pdf"):
    """Create and save a correlation heatmap."""
    sns.set(style=SNS_STYLE, context=SNS_CONTEXT)

    plt.figure(figsize=(5, 4))
    sns.heatmap(
        corr_matrix,
        annot=True,
        fmt=".2f",
        cmap="RdBu_r",
        center=0,
        linewidths=0.5,
        linecolor="lightgray",
        annot_kws={"size": 9, "color": "black"}
    )

    plt.xticks(rotation=45, ha="right", fontsize=9)
    plt.yticks(rotation=0, fontsize=9)
    plt.tight_layout()

    output_path = OUTPUT_DIR / save_name
    plt.savefig(output_path, bbox_inches="tight", dpi=300)
    print(f"Saved heatmap to: {output_path}")
    plt.show()
    plt.close()


def plot_scatter(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    save_name: str = None,
    show_legend: bool = True
):
    """
    Create scatter plot with regression line and correlation statistics.

    Args:
        df: DataFrame with data
        x_col: Column name for x-axis (SWE-bench)
        y_col: Column name for y-axis (Tessera metric)
        save_name: Output filename
        show_legend: Whether to show legend
    """
    x = df[x_col]
    y = df[y_col]

    # Fit regression
    m, b = np.polyfit(x, y, 1)
    r2 = r2_score(y, m * x + b)

    # Compute correlations
    pearson_r = x.corr(y, method="pearson")
    spearman_r = x.corr(y, method="spearman")
    kendall_t = x.corr(y, method="kendall")

    sns.set(style=SNS_STYLE, context=SNS_CONTEXT)

    plt.figure(figsize=(8, 6))

    # Scatter plot - color by model but no per-point labels (legend provided via legend_only.pdf)
    sns.scatterplot(
        data=df,
        x=x_col,
        y=y_col,
        hue="Display_Name",
        palette="tab10",
        s=250,
        edgecolor="black",
        legend=False
    )

    # Regression line
    sns.regplot(
        data=df,
        x=x_col,
        y=y_col,
        scatter=False,
        color="black",
        line_kws={"linestyle": "--", "linewidth": 2}
    )

    # Statistics text box
    text_str = (
        f"Pearson r = {pearson_r:.2f}\n"
        f"Spearman ρ = {spearman_r:.2f}\n"
        f"Kendall τ = {kendall_t:.2f}\n"
    )
    plt.gca().text(
        0.75, 0.2, text_str,
        transform=plt.gca().transAxes,
        fontsize=18, va="top",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.8)
    )

    plt.xlabel(f"{x_col} (%)", fontsize=22)
    plt.ylabel(f"{y_col} (%)", fontsize=22)

    # Fit y-axis to data range with 5% padding
    y_min, y_max = y.min(), y.max()
    y_range = y_max - y_min
    plt.ylim(y_min - 0.05 * y_range, y_max + 0.05 * y_range)

    plt.tight_layout()

    if save_name:
        output_path = OUTPUT_DIR / save_name
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        print(f"Saved scatter plot to: {output_path}")

    plt.show()
    plt.close()


def plot_legend_only(df: pd.DataFrame, save_name: str = "legend_only.pdf"):
    """Create a standalone legend figure for the 7 models."""
    sns.set(style=SNS_STYLE, context=SNS_CONTEXT)

    plt.figure(figsize=(8, 2))
    ax = plt.gca()

    palette = sns.color_palette("tab10", n_colors=len(df))

    for i, model in enumerate(df["Display_Name"].unique()):
        ax.scatter([], [], color=palette[i], edgecolor="black", s=100, label=model)

    ax.axis("off")
    ax.legend(
        loc="center", ncol=4,
        frameon=False,
        fontsize=14,
        markerscale=1.5
    )

    plt.tight_layout()
    output_path = OUTPUT_DIR / save_name
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    print(f"Saved legend to: {output_path}")
    plt.show()
    plt.close()


def generate_all_plots(df_swe: pd.DataFrame, corr_matrix: pd.DataFrame):
    """Generate all plots for the correlation analysis."""
    print("\n" + "=" * 60)
    print("Generating Plots")
    print("=" * 60)

    # Correlation heatmap (all models - need full data)
    print("\n1. Correlation heatmap...")
    plot_correlation_heatmap(corr_matrix)

    # Scatter plots
    print("\n2. Scatter plots...")
    plot_scatter(df_swe, "SWE-bench", "TPR", save_name="scatter_TPR.pdf")
    plot_scatter(df_swe, "SWE-bench", "Cov", save_name="scatter_Cov.pdf")
    plot_scatter(df_swe, "SWE-bench", "IR", save_name="scatter_IR.pdf")

    # Legend
    print("\n3. Legend...")
    plot_legend_only(df_swe)

    print("\nAll plots generated successfully!")


if __name__ == "__main__":
    # Load data and generate plots
    from main import load_all_results, aggregate_metrics, filter_swe_bench_models, compute_correlation_matrix

    all_results = load_all_results()
    df_all_models = aggregate_metrics(all_results)
    df_swe = filter_swe_bench_models(df_all_models)
    corr_matrix = compute_correlation_matrix(df_all_models)

    generate_all_plots(df_swe, corr_matrix)