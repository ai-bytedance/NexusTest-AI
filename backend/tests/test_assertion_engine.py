from __future__ import annotations

from app.services.assertions.engine import AssertionEngine
from app.services.execution.context import ExecutionContext


def test_assertion_engine_successful_evaluations() -> None:
    engine = AssertionEngine()
    context = ExecutionContext(variables={"expected": "world"})
    response_context = {
        "status_code": 200,
        "headers": {"Content-Type": "application/json"},
        "body": "Hello, World!",
        "json": {"greeting": "hello", "numbers": [1, 2, 3]},
    }

    assertions = [
        {"operator": "status_code", "expected": 200},
        {"operator": "equals", "actual": "{{response.jsonpath('$.greeting')}}", "expected": "hello"},
        {"operator": "contains", "actual": "{{response.body}}", "expected": "World"},
        {"operator": "regex_match", "actual": "{{response.body}}", "expected": r"Hello,\s+World"},
        {"operator": "jsonpath_contains", "path": "$.numbers", "expected": 2},
        {"operator": "not_equals", "actual": "{{variables.expected}}", "expected": "planet"},
    ]

    passed, results = engine.evaluate(assertions, response_context, context)

    assert passed is True
    assert all(result.passed for result in results)


def test_assertion_engine_failure_paths() -> None:
    engine = AssertionEngine()
    context = ExecutionContext()
    response_context = {
        "status_code": 404,
        "headers": {"Content-Type": "application/json"},
        "body": "Not Found",
        "json": {"message": "ko"},
    }

    assertions = [
        {"operator": "status_code", "expected": 200},
        {"operator": "jsonpath_equals", "path": "$.message", "expected": "ok"},
    ]

    passed, results = engine.evaluate(assertions, response_context, context)

    assert passed is False
    assert len(results) == 2
    assert results[0].operator == "status_code"
    assert results[0].passed is False
    assert results[1].operator == "jsonpath_equals"
    assert results[1].passed is False
