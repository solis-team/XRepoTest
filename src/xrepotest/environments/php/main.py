"""
Main entry point for PHP environment evaluation.
"""

from base.runner import run_environment
from .evaluator import PHPEvaluator

def main():
    run_environment("php", PHPEvaluator)

if __name__ == "__main__":
    main()
