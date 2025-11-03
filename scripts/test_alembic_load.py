#!/usr/bin/env python3
"""
Test script to simulate Alembic environment loading with various CORS configurations.

This simulates the scenario where Settings() would be called during Alembic env.py load,
which was causing crashes in the original issue.
"""

import os
import sys
import tempfile

# Add the backend directory to the path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.core.config import Settings


def test_alembic_env_simulation():
    """Test various CORS configurations that might be present during Alembic env load."""
    
    print("Testing Alembic environment simulation...")
    print("=" * 60)
    
    # Test cases that simulate various environment states
    test_cases = [
        ("No CORS env vars", {}, None, False),
        ("Empty BACKEND_CORS_ORIGINS", {"cors_origins_raw": ""}, None, False),
        ("Whitespace BACKEND_CORS_ORIGINS", {"cors_origins_raw": "   "}, None, False),
        ("JSON array BACKEND_CORS_ORIGINS", {"cors_origins_raw": '["http://localhost:3000"]'}, None, False),
        ("CSV BACKEND_CORS_ORIGINS", {"cors_origins_raw": "http://localhost:3000,http://127.0.0.1:3000"}, None, False),
        ("Wildcard BACKEND_CORS_ORIGINS", {"cors_origins_raw": "*"}, None, False),
        ("Allow any origin", {"cors_origins_raw": "http://localhost:3000", "allow_any_origin": True}, None, False),
        ("Allow any origin with empty CORS", {"allow_any_origin": True}, None, False),
    ]
    
    passed = 0
    failed = 0
    
    for description, cors_kwargs, env_vars, should_fail in test_cases:
        try:
            # Create Settings with explicit parameters (simulating direct instantiation)
            # This is what would happen in Alembic env.py if we bypass environment loading
            settings = Settings(
                database_url="postgresql+psycopg://test:test@localhost:5432/test",
                redis_url="redis://localhost:6379/0",
                **cors_kwargs
            )
            
            # Check if we got the expected result
            if should_fail:
                print(f"❌ FAIL: {description} (should have failed but didn't)")
                failed += 1
            else:
                print(f"✅ PASS: {description}")
                print(f"   CORS origins: {settings.cors_origins}")
                print(f"   Allow any origin: {settings.allow_any_origin}")
                passed += 1
                    
        except Exception as e:
            if should_fail:
                print(f"✅ PASS: {description} (failed as expected)")
                print(f"   Exception: {type(e).__name__}: {e}")
                passed += 1
            else:
                print(f"❌ FAIL: {description}")
                print(f"   Exception: {type(e).__name__}: {e}")
                failed += 1
        
        print()
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    
    if failed > 0:
        print("⚠️  Some tests failed!")
        return False
    else:
        print("🎉 All tests passed! Alembic env load should work correctly.")
        return True


def test_real_world_docker_scenario():
    """Test the actual Docker Compose scenario from the ticket."""
    
    print("\nTesting real-world Docker scenario...")
    print("=" * 60)
    
    # Simulate the Docker Compose environment
    docker_env = {
        "BACKEND_CORS_ORIGINS": '["http://localhost:8080","http://127.0.0.1:8080","http://192.168.210.129:8080"]',
        "ALLOW_ANY_ORIGIN": "false",
        "DATABASE_URL": "postgresql+psycopg://app:app@postgres:5432/app",
        "REDIS_URL": "redis://redis:6379/0",
    }
    
    try:
        # Save original environment
        original_env = {}
        for key in docker_env:
            original_env[key] = os.environ.get(key)
        
        # Set Docker environment
        for key, value in docker_env.items():
            os.environ[key] = value
        
        # Create Settings (this is what happens in container startup)
        settings = Settings()
        
        print("✅ PASS: Docker Compose scenario")
        print(f"   CORS origins: {settings.cors_origins}")
        print(f"   Allow any origin: {settings.allow_any_origin}")
        
        # Restore original environment
        for key, original_value in original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: Docker Compose scenario")
        print(f"   Exception: {type(e).__name__}: {e}")
        
        # Restore original environment
        for key, original_value in original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value
        
        return False


def main():
    """Main test function."""
    print("Alembic Environment Load Test")
    print("=" * 60)
    print("Testing that Settings() can be instantiated without crashing")
    print("during Alembic env.py load with various CORS configurations.")
    print()
    
    # Run Alembic simulation tests
    alembic_success = test_alembic_env_simulation()
    
    # Run real-world Docker scenario
    docker_success = test_real_world_docker_scenario()
    
    print("\n" + "=" * 60)
    if alembic_success and docker_success:
        print("🎯 All tests passed! The CORS origins parsing issue is fixed.")
        sys.exit(0)
    else:
        print("⚠️  Some tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()