"""
Main entry point for Rust environment evaluation.
"""

from base.runner import run_environment
from .evaluator import RustEvaluator

def main():
    run_environment("rust", RustEvaluator)

if __name__ == "__main__":
    main()
