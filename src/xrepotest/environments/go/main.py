"""
Main entry point for Go environment evaluation.
"""

from base.runner import run_environment
from .evaluator import GoEvaluator

def main():
    run_environment("go", GoEvaluator)

if __name__ == "__main__":
    main()
