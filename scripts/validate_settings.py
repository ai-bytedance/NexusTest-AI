#!/usr/bin/env python3
"""
Validation script for Settings configuration, especially CORS origins parsing.

This script tests various CORS origins input formats to ensure robust parsing
and prevent crashes during application startup.
"""

import json
import os
import sys
from typing import Any

# Add the backend directory to the path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.core.config import Settings


def test_cors_origins_parsing() -> None:
    """Test various CORS origins input formats."""
    
    test_cases = [
        # (description, cors_origins_value, allow_any_origin, expected_result)
        ("Empty string", "", False, ["http://localhost:8080", "http://127.0.0.1:8080"]),
        ("None value", None, False, ["http://localhost:8080", "http://127.0.0.1:8080"]),
        ("Whitespace only", "   ", False, ["http://localhost:8080", "http://127.0.0.1:8080"]),
        ("JSON array", '["http://localhost:3000","http://127.0.0.1:3000"]', False, 
         ["http://localhost:3000", "http://127.0.0.1:3000"]),
        ("CSV string", "http://localhost:3000,http://127.0.0.1:3000", False,
         ["http://localhost:3000", "http://127.0.0.1:3000"]),
        ("Single origin", "http://localhost:3000", False,
         ["http://localhost:3000"]),
        ("Wildcard", "*", False,
         ["*"]),
        ("Allow any origin flag", "http://localhost:3000", True,
         ["*"]),
        ("Mixed CSV with spaces", " http://localhost:3000 , http://127.0.0.1:3000 ", False,
         ["http://localhost:3000", "http://127.0.0.1:3000"]),
        ("Trailing slashes", "http://localhost:3000/,http://127.0.0.1:3000/", False,
         ["http://localhost:3000", "http://127.0.0.1:3000"]),
        ("Localhost without scheme", "localhost:3000,127.0.0.1:3000", False,
         ["http://localhost:3000", "http://127.0.0.1:3000"]),
        ("Empty entries", "http://localhost:3000,,http://127.0.0.1:3000,", False,
         ["http://localhost:3000", "http://127.0.0.1:3000"]),
        ("Duplicates", "http://localhost:3000,http://localhost:3000,http://127.0.0.1:3000", False,
         ["http://localhost:3000", "http://127.0.0.1:3000"]),
        ("Malformed JSON fallback", '["http://localhost:3000", "http://127.0.0.1:3000"', False,
         ['["http://localhost:3000"', '"http://127.0.0.1:3000"']),
        ("All empty", ",,,", False,
         ["http://localhost:8080", "http://127.0.0.1:8080"]),
        ("List input", ["http://localhost:3000", "http://127.0.0.1:3000"], False,
         ["http://localhost:3000", "http://127.0.0.1:3000"]),
        ("Real-world docker example", '["http://localhost:8080","http://127.0.0.1:8080","http://192.168.210.129:8080"]', False,
         ["http://localhost:8080", "http://127.0.0.1:8080", "http://192.168.210.129:8080"]),
    ]
    
    print("Testing CORS origins parsing...")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for description, cors_value, allow_any, expected in test_cases:
        try:
            # Create settings with test values
            settings = Settings(
                cors_origins=cors_value,
                allow_any_origin=allow_any,
                database_url="postgresql+psycopg2://test:test@localhost:5432/test",
                redis_url="redis://localhost:6379/0"
            )
            
            result = settings.cors_origins
            
            if result == expected:
                print(f"✅ PASS: {description}")
                print(f"   Input: {repr(cors_value)}")
                print(f"   Result: {result}")
                passed += 1
            else:
                print(f"❌ FAIL: {description}")
                print(f"   Input: {repr(cors_value)}")
                print(f"   Expected: {expected}")
                print(f"   Got: {result}")
                failed += 1
                
        except Exception as e:
            print(f"❌ ERROR: {description}")
            print(f"   Input: {repr(cors_value)}")
            print(f"   Exception: {type(e).__name__}: {e}")
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


def test_environment_variable_parsing() -> None:
    """Test parsing from environment variables like in real deployment."""
    
    print("\nTesting environment variable parsing...")
    print("=" * 60)
    
    # Test various environment variable formats
    env_test_cases = [
        ("JSON format", '["http://localhost:3000","http://127.0.0.1:3000"]'),
        ("CSV format", "http://localhost:3000,http://127.0.0.1:3000"),
        ("Wildcard", "*"),
        ("Empty", ""),
        ("Single URL", "http://localhost:3000"),
    ]
    
    for description, env_value in env_test_cases:
        try:
            # Temporarily set environment variable
            original_value = os.environ.get("CORS_ORIGINS")
            os.environ["CORS_ORIGINS"] = env_value
            
            # Create settings (will read from environment)
            settings = Settings(
                database_url="postgresql+psycopg2://test:test@localhost:5432/test",
                redis_url="redis://localhost:6379/0"
            )
            
            print(f"✅ PASS: {description}")
            print(f"   CORS_ORIGINS={repr(env_value)}")
            print(f"   Parsed: {settings.cors_origins}")
            
            # Restore original value
            if original_value is not None:
                os.environ["CORS_ORIGINS"] = original_value
            else:
                os.environ.pop("CORS_ORIGINS", None)
                
        except Exception as e:
            print(f"❌ ERROR: {description}")
            print(f"   CORS_ORIGINS={repr(env_value)}")
            print(f"   Exception: {type(e).__name__}: {e}")
            
            # Restore original value
            original_value = os.environ.get("CORS_ORIGINS")
            if original_value is not None:
                os.environ["CORS_ORIGINS"] = original_value
            else:
                os.environ.pop("CORS_ORIGINS", None)
        
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