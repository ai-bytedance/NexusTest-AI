#!/usr/bin/env python3
"""
Test script to verify that the FastAPI application can start successfully
with various CORS configurations.
"""

import os
import sys

# Add the backend directory to the path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

def test_app_startup():
    """Test that the FastAPI app can be created without CORS errors."""
    
    print("Testing FastAPI app startup...")
    print("=" * 60)
    
    # Test various CORS configurations
    test_cases = [
        ("Default configuration", {}),
        ("Empty CORS", {"BACKEND_CORS_ORIGINS": ""}),
        ("JSON array", {"BACKEND_CORS_ORIGINS": '["http://localhost:3000"]'}),
        ("CSV list", {"BACKEND_CORS_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000"}),
        ("Wildcard", {"BACKEND_CORS_ORIGINS": "*"}),
        ("Allow any origin", {"ALLOW_ANY_ORIGIN": "true"}),
    ]
    
    passed = 0
    failed = 0
    
    for description, env_vars in test_cases:
        try:
            # Save original environment
            original_env = {}
            for key in env_vars:
                original_env[key] = os.environ.get(key)
            
            # Set test environment
            for key, value in env_vars.items():
                os.environ[key] = value
            
            # Set required environment variables
            os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/test")
            os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
            
            # Try to import and create the app
            from app.main import create_app
            app = create_app()
            
            print(f"✅ PASS: {description}")
            print(f"   CORS origins: {app.state.settings.cors_origins}")
            print(f"   Allow any origin: {app.state.settings.allow_any_origin}")
            passed += 1
            
            # Restore original environment
            for key, original_value in original_env.items():
                if original_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original_value
                    
        except Exception as e:
            print(f"❌ FAIL: {description}")
            print(f"   Exception: {type(e).__name__}: {e}")
            failed += 1
            
            # Restore original environment
            for key, original_value in original_env.items():
                if original_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original_value
        
        print()
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    
    if failed > 0:
        print("⚠️  Some app startup tests failed!")
        return False
    else:
        print("🎉 All app startup tests passed!")
        return True


def main():
    """Main test function."""
    print("FastAPI App Startup Test")
    print("=" * 60)
    print("Testing that the FastAPI application can be created")
    print("with various CORS configurations without crashing.")
    print()
    
    success = test_app_startup()
    
    print("\n" + "=" * 60)
    if success:
        print("🎯 FastAPI app startup works correctly!")
        sys.exit(0)
    else:
        print("⚠️  Some app startup tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()