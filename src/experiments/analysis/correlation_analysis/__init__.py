"""Correlation analysis package for Tessera metrics vs SWE-bench."""

from .main import (
    load_all_results,
    aggregate_metrics,
    compute_correlation_matrix,
    filter_swe_bench_models,
    compute_metric_correlations,
    main,
    LANGUAGES,
    METRIC_COLS,
    SWE_BENCH_MAPPING,
)

from .plots import (
    plot_correlation_heatmap,
    plot_scatter,
    plot_legend_only,
    generate_all_plots,
)