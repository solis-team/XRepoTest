import pytest
from experiments.evaluation.common.result_contract import (
    success_result,
    error_result,
    is_successful_record,
    SUCCESS_STATUS,
    ERROR_STATUS,
)

def test_success_result_with_content():
    result = success_result("valid response")
    assert result.status == SUCCESS_STATUS
    assert result.response == "valid response"
    assert result.error is None

def test_success_result_with_empty_content():
    result = success_result("")
    assert result.status == ERROR_STATUS
    assert "Empty response" in result.response
    assert result.error == "Empty response from model"

def test_success_result_with_whitespace_content():
    result = success_result("   ")
    assert result.status == ERROR_STATUS
    assert "Empty response" in result.response

def test_success_result_with_none_content():
    result = success_result(None)
    assert result.status == ERROR_STATUS
    assert "Empty response" in result.response

def test_is_successful_record_valid():
    record = {"status": SUCCESS_STATUS, "response": "valid"}
    assert is_successful_record(record) is True

def test_is_successful_record_empty_response():
    record = {"status": SUCCESS_STATUS, "response": ""}
    assert is_successful_record(record) is False

def test_is_successful_record_error_status():
    record = {"status": ERROR_STATUS, "response": "Error: something"}
    assert is_successful_record(record) is False

def test_is_successful_record_legacy_success():
    record = {"response": "valid"}
    assert is_successful_record(record) is True

def test_is_successful_record_legacy_error():
    record = {"response": "Error: failure"}
    assert is_successful_record(record) is False

def test_is_successful_record_legacy_empty():
    record = {"response": ""}
    assert is_successful_record(record) is False

def test_success_result_with_legacy_error():
    result = success_result("Error: something")
    assert result.status == ERROR_STATUS
    assert result.response == "Error: something"
    assert result.error == "Error: something"

def test_is_successful_record_error_string():
    # If success_result is called with an error string, it might have status success but response starting with Error:
    record = {"status": SUCCESS_STATUS, "response": "Error: something went wrong"}
    assert is_successful_record(record) is False
