"""
Main entry point for Julia environment evaluation.
"""

from base.runner import run_environment
from .evaluator import JuliaEvaluator

def main():
    run_environment("julia", JuliaEvaluator)

if __name__ == "__main__":
    main()
