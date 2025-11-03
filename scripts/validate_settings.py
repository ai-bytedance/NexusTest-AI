#!/usr/bin/env python3
"""
Validation script for Settings configuration, especially CORS origins parsing.

This script tests various BACKEND_CORS_ORIGINS input formats to ensure robust parsing
and prevent crashes during application startup.
"""

import json
import os
import sys
from typing import Any

# Add the backend directory to the path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.config import Settings


def _base_kwargs(additional: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "database_url": "postgresql+psycopg://test:test@localhost:5432/test",
        "redis_url": "redis://localhost:6379/0",
    }
    if additional:
        payload.update(additional)
    return payload


def test_cors_origins_parsing() -> None:
    """Test various CORS origins input formats."""

    test_cases: list[dict[str, Any]] = [
        {"description": "Empty string", "raw": "", "expected": []},
        {"description": "None value", "raw": None, "expected": []},
        {
            "description": "JSON array",
            "raw": '["http://localhost:3000","http://127.0.0.1:3000"]',
            "expected": ["http://localhost:3000", "http://127.0.0.1:3000"],
        },
        {
            "description": "CSV string",
            "raw": "http://localhost:3000,http://127.0.0.1:3000",
            "expected": ["http://localhost:3000", "http://127.0.0.1:3000"],
        },
        {
            "description": "Single origin",
            "raw": "http://localhost:3000",
            "expected": ["http://localhost:3000"],
        },
        {"description": "Wildcard", "raw": "*", "expected": ["*"]},
        {
            "description": "Allow any origin flag",
            "raw": "http://localhost:3000",
            "allow_any_origin": True,
            "expected": ["*"],
        },
        {
            "description": "Mixed CSV with spaces",
            "raw": " http://localhost:3000 , http://127.0.0.1:3000 ",
            "expected": ["http://localhost:3000", "http://127.0.0.1:3000"],
        },
        {
            "description": "Trailing slashes",
            "raw": "http://localhost:3000/,http://127.0.0.1:3000/",
            "expected": ["http://localhost:3000", "http://127.0.0.1:3000"],
        },
        {
            "description": "Localhost without scheme",
            "raw": "localhost:3000,127.0.0.1:3000",
            "expected": ["http://localhost:3000", "http://127.0.0.1:3000"],
        },
        {
            "description": "Empty entries",
            "raw": "http://localhost:3000,,http://127.0.0.1:3000,",
            "expected": ["http://localhost:3000", "http://127.0.0.1:3000"],
        },
        {
            "description": "Duplicates",
            "raw": "http://localhost:3000,http://localhost:3000",
            "expected": ["http://localhost:3000"],
        },
        {
            "description": "Malformed JSON fallback",
            "raw": '["http://localhost:3000", "http://127.0.0.1:3000"',
            "expected": ["http://localhost:3000", "http://127.0.0.1:3000"],
        },
        {"description": "All empty", "raw": ",,,", "expected": []},
        {
            "description": "Direct list input",
            "direct": ["http://localhost:3000", "http://127.0.0.1:3000/"],
            "expected": ["http://localhost:3000", "http://127.0.0.1:3000"],
        },
        {
            "description": "Direct string input",
            "direct": "http://localhost:3000/",
            "expected": ["http://localhost:3000"],
        },
        {
            "description": "Allow any origin with empty raw",
            "raw": "",
            "allow_any_origin": True,
            "expected": ["*"],
        },
    ]

    print("Testing CORS origins parsing...")
    print("=" * 60)

    passed = 0
    failed = 0

    for case in test_cases:
        description: str = case["description"]
        allow_any_origin: bool = case.get("allow_any_origin", False)
        kwargs: dict[str, Any] = {"allow_any_origin": allow_any_origin}
        if "raw" in case:
            kwargs["cors_origins_raw"] = case["raw"]
        if "direct" in case:
            kwargs["cors_origins"] = case["direct"]

        try:
            settings = Settings(**_base_kwargs(kwargs))
            result = settings.cors_origins

            if result == case["expected"]:
                print(f"✅ PASS: {description}")
            else:
                print(f"❌ FAIL: {description}")
                print(f"   Expected: {case['expected']}")
                print(f"   Got: {result}")
                failed += 1
                _print_case_inputs(case)
                continue

            _print_case_inputs(case)
            print(f"   Result: {result}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"❌ ERROR: {description}")
            _print_case_inputs(case)
            print(f"   Exception: {type(exc).__name__}: {exc}")
            failed += 1

        print()

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")

    if failed > 0:
        print("⚠️  Some tests failed!")
        sys.exit(1)
    else:
        print("🎉 All tests passed!")
        sys.exit(0)


def _print_case_inputs(case: dict[str, Any]) -> None:
    if "raw" in case:
        print(f"   BACKEND_CORS_ORIGINS={repr(case['raw'])}")
    if "direct" in case:
        print(f"   direct_cors_origins={repr(case['direct'])}")
    if case.get("allow_any_origin"):
        print("   ALLOW_ANY_ORIGIN=True")


def test_environment_variable_parsing() -> None:
    """Test parsing from environment variables like in real deployment."""

    print("\nTesting environment variable parsing...")
    print("=" * 60)

    env_test_cases = [
        ("JSON format", json.dumps(["http://localhost:3000", "http://127.0.0.1:3000"])),
        ("CSV format", "http://localhost:3000,http://127.0.0.1:3000"),
        ("Wildcard", "*"),
        ("Empty", ""),
        ("Single URL", "http://localhost:3000"),
    ]

    for description, env_value in env_test_cases:
        original_value = os.environ.get("BACKEND_CORS_ORIGINS")
        try:
            os.environ["BACKEND_CORS_ORIGINS"] = env_value

            settings = Settings(**_base_kwargs(None))
            print(f"✅ PASS: {description}")
            print(f"   BACKEND_CORS_ORIGINS={repr(env_value)}")
            print(f"   Parsed: {settings.cors_origins}")
        except Exception as exc:  # noqa: BLE001
            print(f"❌ ERROR: {description}")
            print(f"   BACKEND_CORS_ORIGINS={repr(env_value)}")
            print(f"   Exception: {type(exc).__name__}: {exc}")
        finally:
            if original_value is not None:
                os.environ["BACKEND_CORS_ORIGINS"] = original_value
            else:
                os.environ.pop("BACKEND_CORS_ORIGINS", None)

        print()


def main() -> None:
    """Main validation function."""
    print("Settings Validation Script")
    print("=" * 60)
    print("Testing robust CORS origins parsing to prevent startup crashes")
    print()

    # Test direct value parsing
    test_cors_origins_parsing()

    # Test environment variable parsing
    test_environment_variable_parsing()

    print("\n🎯 Validation complete!")


if __name__ == "__main__":
    main()
