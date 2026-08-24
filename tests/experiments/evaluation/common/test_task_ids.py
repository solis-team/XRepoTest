from experiments.evaluation.common.task_ids import normalize_task_id, task_id_sort_key


def test_normalize_task_id_converts_numeric_strings() -> None:
    assert normalize_task_id("42") == 42
    assert normalize_task_id(" 007 ") == 7
    assert normalize_task_id("abc-1") == "abc-1"


def test_task_id_sort_key_orders_numeric_before_text() -> None:
    values = ["b", "10", 2, 1, "a"]
    sorted_values = sorted(values, key=task_id_sort_key)
    assert sorted_values == [1, 2, "10", "a", "b"]

