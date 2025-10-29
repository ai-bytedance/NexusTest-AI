from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import dataclass

from app.services.execution.policy import ExecutionPolicySnapshot


class _NullContext:
    def __enter__(self) -> "_NullContext":  # pragma: no cover - trivial
        return self

    def __exit__(self, *exc_info: object) -> bool:  # pragma: no cover - trivial
        return False


@dataclass
class _SemaphoreWrapper:
    capacity: int
    semaphore: threading.BoundedSemaphore


class _SemaphoreContext:
    def __init__(self, semaphore: threading.BoundedSemaphore) -> None:
        self._semaphore = semaphore

    def __enter__(self) -> "_SemaphoreContext":
        self._semaphore.acquire()
        return self

    def __exit__(self, *exc_info: object) -> bool:
        self._semaphore.release()
        return False


class TokenBucket:
    def __init__(self, rate: float, capacity: float | None = None) -> None:
        if rate <= 0:
            raise ValueError("Token bucket rate must be greater than zero")
        self._rate = float(rate)
        self._capacity = float(capacity) if capacity and capacity > 0 else float(rate)
        self._tokens = self._capacity
        self._updated_at = time.monotonic()
        self._lock = threading.Lock()

    @property
    def rate(self) -> float:
        return self._rate

    def consume(self, tokens: float = 1.0) -> float:
        target = max(tokens, 0.0)
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._updated_at
            if elapsed > 0:
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                self._updated_at = now
            if self._tokens >= target:
                self._tokens -= target
                return 0.0
            deficit = target - self._tokens
            self._tokens = 0.0
            return deficit / self._rate


class PerHostRateLimiter:
    def __init__(self, rate: float) -> None:
        self._rate = max(rate, 1e-6)
        self._capacity = max(self._rate, 1.0)
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    @property
    def rate(self) -> float:
        return self._rate

    def wait_time(self, host: str) -> float:
        normalized = (host or "default").strip().lower() or "default"
        with self._lock:
            bucket = self._buckets.get(normalized)
            if bucket is None or not math.isclose(bucket.rate, self._rate, rel_tol=1e-6):
                bucket = TokenBucket(rate=self._rate, capacity=self._capacity)
                self._buckets[normalized] = bucket
        return bucket.consume()


class CircuitBreakerState:
    def __init__(self, threshold: int, cooldown_seconds: float) -> None:
        self._threshold = max(1, threshold)
        self._cooldown = max(1.0, cooldown_seconds)
        self._failure_count = 0
        self._open_until = 0.0
        self._lock = threading.Lock()

    def record_failure(self) -> bool:
        with self._lock:
            self._failure_count += 1
            if self._failure_count >= self._threshold:
                self._failure_count = 0
                self._open_until = time.monotonic() + self._cooldown
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._open_until = 0.0

    def remaining(self) -> float:
        with self._lock:
            if self._open_until <= 0:
                return 0.0
            remaining = self._open_until - time.monotonic()
            if remaining <= 0:
                self._open_until = 0.0
                return 0.0
            return remaining

    def update_policy(self, threshold: int, cooldown: float) -> None:
        with self._lock:
            self._threshold = max(1, threshold)
            self._cooldown = max(1.0, cooldown)


@dataclass
class _CircuitRegistry:
    threshold: int
    cooldown: float
    states: dict[str, CircuitBreakerState]
    lock: threading.Lock

    def get_state(self, host: str) -> CircuitBreakerState:
        normalized = (host or "default").strip().lower() or "default"
        with self.lock:
            state = self.states.get(normalized)
            if state is None:
                state = CircuitBreakerState(self.threshold, self.cooldown)
                self.states[normalized] = state
            else:
                state.update_policy(self.threshold, self.cooldown)
            return state


class ExecutionPolicyRuntime:
    _semaphore_lock = threading.Lock()
    _rate_lock = threading.Lock()
    _circuit_lock = threading.Lock()
    _semaphores: dict[str, _SemaphoreWrapper] = {}
    _rate_limiters: dict[str, PerHostRateLimiter] = {}
    _circuit_registries: dict[str, _CircuitRegistry] = {}

    def __init__(self, snapshot: ExecutionPolicySnapshot) -> None:
        self.snapshot = snapshot

    def acquire_slot(self):  # pragma: no cover - thin wrapper
        wrapper = self._ensure_semaphore()
        if wrapper is None:
            return _NullContext()
        return _SemaphoreContext(wrapper.semaphore)

    def rate_limit_delay(self, host: str) -> float:
        limiter = self._ensure_rate_limiter()
        if limiter is None:
            return 0.0
        return limiter.wait_time(host)

    def circuit_remaining(self, host: str) -> float:
        registry = self._ensure_circuit_registry()
        if registry is None:
            return 0.0
        return registry.get_state(host).remaining()

    def record_failure(self, host: str) -> tuple[float, bool]:
        registry = self._ensure_circuit_registry()
        if registry is None:
            return 0.0, False
        state = registry.get_state(host)
        opened = state.record_failure()
        return state.remaining(), opened

    def record_success(self, host: str) -> None:
        registry = self._ensure_circuit_registry()
        if registry is None:
            return
        registry.get_state(host).record_success()

    def backoff_delay(self, retry_number: int) -> float:
        if retry_number <= 0:
            return 0.0
        base = self.snapshot.retry_backoff.base_seconds * (2 ** (retry_number - 1))
        base = min(base, self.snapshot.retry_backoff.max_seconds)
        jitter_span = base * self.snapshot.retry_backoff.jitter_ratio
        jitter = random.uniform(0.0, jitter_span) if jitter_span > 0 else 0.0
        return base + jitter

    def _ensure_semaphore(self) -> _SemaphoreWrapper | None:
        capacity = self.snapshot.max_concurrency
        if capacity is None or capacity <= 0:
            return None
        key = self.snapshot.key
        with self._semaphore_lock:
            wrapper = self._semaphores.get(key)
            if wrapper is None or wrapper.capacity != capacity:
                wrapper = _SemaphoreWrapper(capacity=capacity, semaphore=threading.BoundedSemaphore(capacity))
                self._semaphores[key] = wrapper
            return wrapper

    def _ensure_rate_limiter(self) -> PerHostRateLimiter | None:
        rate = self.snapshot.per_host_qps
        if rate is None or rate <= 0:
            return None
        key = self.snapshot.key
        with self._rate_lock:
            limiter = self._rate_limiters.get(key)
            if limiter is None or not math.isclose(limiter.rate, rate, rel_tol=1e-6):
                limiter = PerHostRateLimiter(rate)
                self._rate_limiters[key] = limiter
            return limiter

    def _ensure_circuit_registry(self) -> _CircuitRegistry | None:
        threshold = self.snapshot.circuit_breaker_threshold
        if threshold <= 0:
            return None
        cooldown = self.snapshot.retry_backoff.cooldown_seconds
        key = self.snapshot.key
        with self._circuit_lock:
            registry = self._circuit_registries.get(key)
            if registry is None:
                registry = _CircuitRegistry(
                    threshold=threshold,
                    cooldown=cooldown,
                    states={},
                    lock=threading.Lock(),
                )
                self._circuit_registries[key] = registry
            else:
                registry.threshold = threshold
                registry.cooldown = cooldown
            return registry


__all__ = [
    "ExecutionPolicyRuntime",
]
