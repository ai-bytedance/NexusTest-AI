import json

from app.core.config import Settings


class TestCorsOriginsParsing:
    def _create_settings(self, **kwargs) -> Settings:
        base = {
            "database_url": "postgresql+psycopg://test:test@localhost:5432/test",
            "redis_url": "redis://localhost:6379/0",
        }
        base.update(kwargs)
        return Settings(**base)

    def test_defaults_to_empty_list_when_unset(self) -> None:
        settings = self._create_settings()
        assert settings.cors_origins == []

    def test_empty_string_env_yields_empty_list(self) -> None:
        settings = self._create_settings(cors_origins_raw="")
        assert settings.cors_origins == []

    def test_wildcard_env_sets_single_wildcard(self) -> None:
        settings = self._create_settings(cors_origins_raw="*")
        assert settings.cors_origins == ["*"]

    def test_json_array_parsing(self) -> None:
        raw = json.dumps(["http://localhost:3000", "http://127.0.0.1:3000"])
        settings = self._create_settings(cors_origins_raw=raw)
        assert settings.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]

    def test_comma_separated_list_parsing(self) -> None:
        settings = self._create_settings(cors_origins_raw="http://localhost:3000, http://127.0.0.1:3000/")
        assert settings.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]

    def test_malformed_json_falls_back_to_csv(self) -> None:
        malformed = '["http://localhost:3000", "http://127.0.0.1:3000"'
        settings = self._create_settings(cors_origins_raw=malformed)
        assert settings.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]

    def test_duplicates_removed(self) -> None:
        settings = self._create_settings(cors_origins_raw="http://localhost:3000,http://localhost:3000")
        assert settings.cors_origins == ["http://localhost:3000"]

    def test_localhost_without_scheme_gets_http(self) -> None:
        settings = self._create_settings(cors_origins_raw="localhost:3000,127.0.0.1:3000")
        assert settings.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]

    def test_wildcard_with_specific_origins_collapses_to_wildcard(self) -> None:
        settings = self._create_settings(cors_origins_raw="*,http://localhost:3000")
        assert settings.cors_origins == ["*"]

    def test_allow_any_origin_overrides_configuration(self) -> None:
        settings = self._create_settings(cors_origins_raw="http://localhost:3000", allow_any_origin=True)
        assert settings.cors_origins == ["*"]

    def test_allow_any_origin_without_explicit_origins(self) -> None:
        settings = self._create_settings(allow_any_origin=True)
        assert settings.cors_origins == ["*"]

    def test_direct_list_population_normalizes_entries(self) -> None:
        settings = self._create_settings(cors_origins=["http://localhost:3000", "http://127.0.0.1:3000/"])
        assert settings.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]

    def test_direct_string_population_is_normalized(self) -> None:
        settings = self._create_settings(cors_origins="http://localhost:3000/")
        assert settings.cors_origins == ["http://localhost:3000"]
