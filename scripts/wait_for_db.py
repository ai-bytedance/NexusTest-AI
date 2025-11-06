#!/usr/bin/env python3
"""Block until the primary database is reachable."""

from __future__ import annotations

import os
import sys
import time
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

DEFAULT_INTERVAL_SECONDS = 2.0
DEFAULT_TIMEOUT_SECONDS = 120.0
ENGINE_OPTIONS = {
    "pool_pre_ping": True,
    "pool_size": 1,
    "max_overflow": 0,
    "future": True,
}


def _timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _log(message: str, *, stream: Optional[object] = None) -> None:
    target = stream or sys.stdout
    target.write(f"[wait_for_db] {_timestamp()} {message}\n")
    target.flush()


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        _log(
            f"invalid value for {name!r} ({value!r}); falling back to {default}",
            stream=sys.stderr,
        )
        return default


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        _log(
            f"invalid value for {name!r} ({value!r}); falling back to {default}",
            stream=sys.stderr,
        )
        return default


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        _log("DATABASE_URL environment variable is not set", stream=sys.stderr)
        return 1

    interval_seconds = max(_get_float("DB_WAIT_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS), 0.1)
    timeout_seconds = _get_float("DB_WAIT_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
    max_attempts = _get_int("DB_WAIT_MAX_ATTEMPTS", 0)

    try:
        masked_url = make_url(database_url).render_as_string(hide_password=True)
    except Exception:  # pragma: no cover - defensive
        masked_url = database_url

    deadline: Optional[float]
    if timeout_seconds <= 0:
        deadline = None
    else:
        deadline = time.monotonic() + timeout_seconds

    attempts_desc = "unlimited" if max_attempts <= 0 else str(max_attempts)
    if deadline is None:
        _log(
            f"waiting for database {masked_url} (no timeout, interval={interval_seconds:.1f}s, max_attempts={attempts_desc})"
        )
    else:
        _log(
            f"waiting for database {masked_url} (timeout={timeout_seconds:.1f}s, interval={interval_seconds:.1f}s, max_attempts={attempts_desc})"
        )

    engine = create_engine(database_url, **ENGINE_OPTIONS)

    attempt = 1
    while True:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            engine.dispose()
            _log(f"attempt {attempt}: database unavailable ({exc})", stream=sys.stderr)
            if max_attempts and attempt >= max_attempts:
                _log("giving up because DB_WAIT_MAX_ATTEMPTS was exceeded", stream=sys.stderr)
                return 1
            if deadline and time.monotonic() >= deadline:
                _log(
                    "giving up because DB_WAIT_TIMEOUT_SECONDS was exceeded",
                    stream=sys.stderr,
                )
                return 1
            time.sleep(interval_seconds)
            attempt += 1
            continue
        except Exception as exc:  # pragma: no cover - defensive
            engine.dispose()
            _log(f"attempt {attempt}: unexpected error ({exc})", stream=sys.stderr)
            if max_attempts and attempt >= max_attempts:
                _log("giving up because DB_WAIT_MAX_ATTEMPTS was exceeded", stream=sys.stderr)
                return 1
            if deadline and time.monotonic() >= deadline:
                _log(
                    "giving up because DB_WAIT_TIMEOUT_SECONDS was exceeded",
                    stream=sys.stderr,
                )
                return 1
            time.sleep(interval_seconds)
            attempt += 1
            continue

        _log(
            f"database ready after {attempt} attempt{'s' if attempt != 1 else ''}; proceeding",
        )
        engine.dispose()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
