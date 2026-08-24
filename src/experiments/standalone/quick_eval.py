from llm_generation import load_and_evaluate_tests

# Evaluate all generated tests
results = load_and_evaluate_tests(
    input_dir="generated_tests",
    model="gemini-2.5-flash"  # Optional: evaluate specific model
)

print("\n" + "="*50)
print("EVALUATION RESULTS")
print("="*50)
for lang, stats in results.items():
    print(f"\n{lang}:")
    print(f"  Pass Rate: {stats['pass_rate']:.1f}%")
    print(f"  Avg Coverage: {stats['avg_coverage']:.1f}%")
    print(f"  Passed: {stats['passed']}/{stats['total']} tests")