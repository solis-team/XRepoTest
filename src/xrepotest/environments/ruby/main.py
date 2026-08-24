"""
Main entry point for Ruby environment evaluation.
"""

from base.runner import run_environment
from .evaluator import RubyEvaluator

def main():
    run_environment("ruby", RubyEvaluator)

if __name__ == "__main__":
    main()
