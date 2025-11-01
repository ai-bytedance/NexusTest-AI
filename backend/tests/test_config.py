import json
import pytest
from pydantic import ValidationError

from app.core.config import Settings


class TestCorsOriginsValidator:
    """Test cases for the CORS origins field validator."""

    def test_none_value_returns_defaults(self):
        """Test that None value returns default origins."""
        settings = Settings(cors_origins=None)
        expected = ["http://localhost:8080", "http://127.0.0.1:8080"]
        assert settings.cors_origins == expected

    def test_empty_string_returns_defaults(self):
        """Test that empty string returns default origins."""
        settings = Settings(cors_origins="")
        expected = ["http://localhost:8080", "http://127.0.0.1:8080"]
        assert settings.cors_origins == expected

    def test_whitespace_only_string_returns_defaults(self):
        """Test that whitespace-only string returns default origins."""
        settings = Settings(cors_origins="   ")
        expected = ["http://localhost:8080", "http://127.0.0.1:8080"]
        assert settings.cors_origins == expected

    def test_json_array_string(self):
        """Test parsing JSON array string."""
        json_str = '["http://localhost:8080", "http://127.0.0.1:8080"]'
        settings = Settings(cors_origins=json_str)
        expected = ["http://localhost:8080", "http://127.0.0.1:8080"]
        assert settings.cors_origins == expected

    def test_json_array_with_trailing_slashes(self):
        """Test that trailing slashes are removed from JSON origins."""
        json_str = '["http://localhost:8080/", "http://127.0.0.1:8080/"]'
        settings = Settings(cors_origins=json_str)
        expected = ["http://localhost:8080", "http://127.0.0.1:8080"]
        assert settings.cors_origins == expected

    def test_malformed_json_fallback_to_csv(self):
        """Test that malformed JSON falls back to CSV parsing."""
        malformed_json = '["http://localhost:8080", "http://127.0.0.1:8080"'  # Missing closing bracket
        settings = Settings(cors_origins=malformed_json)
        # Should fall back to CSV parsing
        expected = ['["http://localhost:8080"', '"http://127.0.0.1:8080"']
        assert settings.cors_origins == expected

    def test_csv_string(self):
        """Test parsing comma-separated string."""
        csv_str = "http://localhost:8080,http://127.0.0.1:8080"
        settings = Settings(cors_origins=csv_str)
        expected = ["http://localhost:8080", "http://127.0.0.1:8080"]
        assert settings.cors_origins == expected

    def test_csv_with_spaces(self):
        """Test parsing CSV string with spaces."""
        csv_str = " http://localhost:8080 , http://127.0.0.1:8080 "
        settings = Settings(cors_origins=csv_str)
        expected = ["http://localhost:8080", "http://127.0.0.1:8080"]
        assert settings.cors_origins == expected

    def test_csv_with_trailing_slashes(self):
        """Test that trailing slashes are removed from CSV origins."""
        csv_str = "http://localhost:8080/,http://127.0.0.1:8080/"
        settings = Settings(cors_origins=csv_str)
        expected = ["http://localhost:8080", "http://127.0.0.1:8080"]
        assert settings.cors_origins == expected

    def test_list_input(self):
        """Test parsing list input."""
        origins_list = ["http://localhost:8080", "http://127.0.0.1:8080"]
        settings = Settings(cors_origins=origins_list)
        expected = ["http://localhost:8080", "http://127.0.0.1:8080"]
        assert settings.cors_origins == expected

    def test_list_with_trailing_slashes(self):
        """Test that trailing slashes are removed from list origins."""
        origins_list = ["http://localhost:8080/", "http://127.0.0.1:8080/"]
        settings = Settings(cors_origins=origins_list)
        expected = ["http://localhost:8080", "http://127.0.0.1:8080"]
        assert settings.cors_origins == expected

    def test_duplicate_removal(self):
        """Test that duplicate origins are removed while preserving order."""
        csv_str = "http://localhost:8080,http://127.0.0.1:8080,http://localhost:8080"
        settings = Settings(cors_origins=csv_str)
        expected = ["http://localhost:8080", "http://127.0.0.1:8080"]
        assert settings.cors_origins == expected

    def test_empty_entries_filtered(self):
        """Test that empty entries are filtered out."""
        csv_str = "http://localhost:8080,,http://127.0.0.1:8080,"
        settings = Settings(cors_origins=csv_str)
        expected = ["http://localhost:8080", "http://127.0.0.1:8080"]
        assert settings.cors_origins == expected

    def test_wildcard_only(self):
        """Test that wildcard alone is allowed."""
        settings = Settings(cors_origins="*")
        assert settings.cors_origins == ["*"]

    def test_wildcard_with_others_raises_error(self):
        """Test that wildcard with other origins raises error."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(cors_origins="*,http://localhost:8080")
        assert "CORS_ORIGINS cannot include '*' alongside specific origins" in str(exc_info.value)

    def test_non_string_items_converted(self):
        """Test that non-string items are converted to strings."""
        # This would be unusual but should be handled gracefully
        origins_list = ["http://localhost:8080", 123, "http://127.0.0.1:8080"]
        settings = Settings(cors_origins=origins_list)
        expected = ["http://localhost:8080", "123", "http://127.0.0.1:8080"]
        assert settings.cors_origins == expected

    def test_json_not_array_fallback_to_csv(self):
        """Test that JSON not being an array falls back to CSV parsing."""
        json_str = '"http://localhost:8080"'  # JSON string, not array
        settings = Settings(cors_origins=json_str)
        # Should fall back to CSV parsing
        expected = ['"http://localhost:8080"']
        assert settings.cors_origins == expected

    def test_all_empty_entries_returns_defaults(self):
        """Test that all empty entries return defaults."""
        csv_str = ",,,"
        settings = Settings(cors_origins=csv_str)
        expected = ["http://localhost:8080", "http://127.0.0.1:8080"]
        assert settings.cors_origins == expected

    def test_complex_real_world_example(self):
        """Test a complex real-world example from the ticket."""
        json_str = '["http://localhost:8080","http://127.0.0.1:8080","http://192.168.210.129:8080"]'
        settings = Settings(cors_origins=json_str)
        expected = ["http://localhost:8080", "http://127.0.0.1:8080", "http://192.168.210.129:8080"]
        assert settings.cors_origins == expected