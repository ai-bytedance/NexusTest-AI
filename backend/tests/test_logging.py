from app.logging import get_logger


def test_get_logger_accepts_optional_name() -> None:
    named_logger = get_logger(__name__)
    unnamed_logger = get_logger()

    for logger in (named_logger, unnamed_logger):
        assert hasattr(logger, "info")
        assert callable(logger.info)
        assert hasattr(logger, "bind")
        assert callable(logger.bind)
