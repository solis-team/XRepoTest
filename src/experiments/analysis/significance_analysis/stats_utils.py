from dataclasses import asdict, dataclass
from typing import Protocol, Sequence

import numpy as np
from numpy.typing import NDArray


class SupportsTestOutcome(Protocol):
    test_id: str
    passed: bool


@dataclass(slots=True)
class ConfidenceInterval:
    lower: float
    upper: float
    mean: float
    std: float

    @property
    def cv(self) -> float:
        if self.mean == 0:
            return float("inf")
        return self.std / self.mean


@dataclass(slots=True)
class McNemarResult:
    model_a: str
    model_b: str
    n_tests: int
    a_only: int
    b_only: int
    both_pass: int
    both_fail: int
    chi_square: float
    p_value: float
    significant: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def __str__(self) -> str:
        sig_marker = "***" if self.p_value < 0.001 else ("**" if self.p_value < 0.01 else ("*" if self.significant else ""))
        return f"{self.model_a} vs {self.model_b}: χ²={self.chi_square:.3f}, p={self.p_value:.4f}{sig_marker}"


def align_test_results(
    tests_a: Sequence[SupportsTestOutcome],
    tests_b: Sequence[SupportsTestOutcome],
) -> tuple[NDArray[np.bool_], NDArray[np.bool_]]:
    results_a = {test.test_id: test.passed for test in tests_a}
    results_b = {test.test_id: test.passed for test in tests_b}

    common_ids = sorted(set(results_a) & set(results_b))
    if not common_ids:
        return np.array([], dtype=bool), np.array([], dtype=bool)

    aligned_a = np.array([results_a[test_id] for test_id in common_ids], dtype=bool)
    aligned_b = np.array([results_b[test_id] for test_id in common_ids], dtype=bool)
    return aligned_a, aligned_b
