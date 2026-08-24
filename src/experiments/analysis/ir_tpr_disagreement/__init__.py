"""IR vs TPR Disagreement Analysis.

Measures how often the Invocation Rate (IR) check disagrees with the Test Pass Rate (TPR).
Specifically: among test suites that pass (compilation=true AND tests=true),
what fraction fail the invocation check (invocation=false)?

This demonstrates that TPR alone overestimates test quality — many "passing" tests
don't actually invoke the focal function, and IR captures this missing dimension.
"""
