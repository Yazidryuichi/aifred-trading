"""Production resilience utilities for the AIFred trading system.

Provides circuit breaking, rate limiting, retry with backoff, connection
pooling, and health monitoring for all external service integrations
(Hyperliquid, DeFiLlama, Etherscan, etc.).

Usage examples:

    # Circuit breaker around an exchange call
    cb = CircuitBreaker(name="hyperliquid", failure_threshold=5)
    async with cb:
        result = await exchange.place_order(...)

    # Rate limiter for API endpoints
    limiter = RateLimiter(max_tokens=10, refill_rate=2.0)
    await limiter.acquire()
    response = await session.get(url)

    # Retry decorator with exponential backoff
    @retry_with_backoff(max_retries=3, retry_on=(ConnectionError, TimeoutError))
    async def fetch_price(symbol: str) -> float:
        ...

    # Connection pool with health checks
    pool = ConnectionPool(base_url="https://api.hyperliquid.xyz")
    await pool.start()
    session = await pool.get_session()

    # Health monitor for all services
    monitor = HealthMonitor(check_interval=30.0)
    monitor.register_service("hyperliquid", hl_connector.ping)
    report = await monitor.get_health_report()
"""

import asyncio
import enum
import functools
import logging
import random
import time
from dataclasses import dataclass, field
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
)

import aiohttp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------

class CircuitState(enum.Enum):
    """Circuit breaker states."""
    CLOSED = "closed"        # Normal operation, calls pass through
    OPEN = "open"            # Failing, all calls rejected immediately
    HALF_OPEN = "half_open"  # Testing recovery, limited calls allowed


class CircuitBreakerOpen(Exception):
    """Raised when a call is rejected because the circuit is open."""

    def __init__(self, name: str, remaining_seconds: float):
        self.name = name
        self.remaining_seconds = remaining_seconds
        super().__init__(
            f"Circuit breaker '{name}' is OPEN. "
            f"Recovery in {remaining_seconds:.1f}s."
        )


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures on external services.

    States:
        CLOSED  -- Normal. Calls pass through. Failures are counted.
        OPEN    -- Too many failures. All calls rejected immediately.
        HALF_OPEN -- Recovery probe. A limited number of calls are allowed
                     through. If enough succeed, the circuit closes. If any
                     fail, it reopens.

    Can be used as an async context manager or as a decorator::

        # Context manager
        async with circuit_breaker:
            await do_something()

        # Decorator
        @circuit_breaker
        async def do_something():
            ...

    Args:
        name: Human-readable name for logging.
        failure_threshold: Consecutive failures before the circuit opens.
        recovery_timeout: Seconds to wait in OPEN before moving to HALF_OPEN.
        success_threshold: Successes needed in HALF_OPEN to close the circuit.
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count: int = 0
        self._success_count: int = 0
        self._last_failure_time: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Current circuit state (may transition OPEN -> HALF_OPEN on read)."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                # Don't transition here -- let _check_state handle it under lock
                return CircuitState.OPEN
        return self._state

    async def _check_state(self) -> None:
        """Evaluate whether the call should be allowed. Raises on rejection."""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return

            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._transition(CircuitState.HALF_OPEN)
                    self._success_count = 0
                    return
                raise CircuitBreakerOpen(
                    self.name,
                    self.recovery_timeout - elapsed,
                )

            # HALF_OPEN -- allow the call through for probing
            return

    async def _record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._transition(CircuitState.CLOSED)
            # In CLOSED state, reset failure count on success
            self._failure_count = 0

    async def _record_failure(self) -> None:
        """Record a failed call."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open immediately reopens
                self._transition(CircuitState.OPEN)
                self._last_failure_time = time.monotonic()
                return

            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._transition(CircuitState.OPEN)
                self._last_failure_time = time.monotonic()

    def _transition(self, new_state: CircuitState) -> None:
        """Transition to a new state with logging."""
        old_state = self._state
        self._state = new_state
        if old_state != new_state:
            logger.warning(
                "Circuit breaker '%s': %s -> %s "
                "(failures=%d, successes=%d)",
                self.name,
                old_state.value,
                new_state.value,
                self._failure_count,
                self._success_count,
            )

    # -- Async context manager interface --

    async def __aenter__(self) -> "CircuitBreaker":
        await self._check_state()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is None:
            await self._record_success()
        else:
            await self._record_failure()

    # -- Decorator interface --

    def __call__(self, fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        """Use as a decorator: @circuit_breaker."""

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            async with self:
                return await fn(*args, **kwargs)

        return wrapper

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        logger.info("Circuit breaker '%s' manually reset to CLOSED", self.name)


# ---------------------------------------------------------------------------
# RateLimiter (token bucket)
# ---------------------------------------------------------------------------

class RateLimiter:
    """Token-bucket rate limiter for API endpoints.

    Supports bursts up to ``max_tokens`` and refills at ``refill_rate``
    tokens per second. ``acquire()`` is async and will sleep until enough
    tokens are available.

    Args:
        max_tokens: Maximum burst capacity (bucket size).
        refill_rate: Tokens added per second.
        name: Optional name for logging.
    """

    def __init__(
        self,
        max_tokens: float = 10.0,
        refill_rate: float = 2.0,
        name: str = "default",
    ) -> None:
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.name = name

        self._tokens: float = max_tokens
        self._last_refill: float = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        """Add tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self.max_tokens,
            self._tokens + elapsed * self.refill_rate,
        )
        self._last_refill = now

    async def acquire(self, tokens: float = 1.0) -> None:
        """Acquire ``tokens`` from the bucket, waiting if necessary.

        Args:
            tokens: Number of tokens to consume. Defaults to 1.

        Raises:
            ValueError: If requested tokens exceed bucket capacity.
        """
        if tokens > self.max_tokens:
            raise ValueError(
                f"Requested {tokens} tokens exceeds bucket capacity "
                f"of {self.max_tokens} for rate limiter '{self.name}'"
            )

        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                # Calculate wait time for enough tokens
                deficit = tokens - self._tokens
                wait_time = deficit / self.refill_rate

            logger.debug(
                "Rate limiter '%s': waiting %.2fs for %.1f tokens",
                self.name, wait_time, tokens,
            )
            await asyncio.sleep(wait_time)

    @property
    def available_tokens(self) -> float:
        """Current number of available tokens (approximate, no lock)."""
        elapsed = time.monotonic() - self._last_refill
        return min(self.max_tokens, self._tokens + elapsed * self.refill_rate)


# ---------------------------------------------------------------------------
# RetryWithBackoff
# ---------------------------------------------------------------------------

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter: bool = True
    retry_on: Tuple[Type[BaseException], ...] = (Exception,)


class RetryExhausted(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, attempts: int, last_exception: BaseException):
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(
            f"All {attempts} retry attempts exhausted. "
            f"Last error: {last_exception}"
        )


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
    retry_on: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable:
    """Decorator for async functions with exponential backoff and jitter.

    Retries the decorated function on specified exception types, using
    exponential backoff (``base_delay * 2^attempt``) capped at ``max_delay``,
    with optional random jitter to prevent thundering-herd effects.

    Args:
        max_retries: Maximum number of retry attempts (not counting the
                     initial call).
        base_delay: Initial delay in seconds before the first retry.
        max_delay: Maximum delay in seconds between retries.
        jitter: If True, add random jitter (0 to 100% of delay).
        retry_on: Tuple of exception types that trigger a retry.

    Example::

        @retry_with_backoff(max_retries=3, retry_on=(ConnectionError, TimeoutError))
        async def fetch_price(symbol: str) -> float:
            ...
    """

    def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Optional[BaseException] = None

            for attempt in range(max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except retry_on as exc:
                    last_exception = exc
                    if attempt == max_retries:
                        logger.error(
                            "Retry exhausted for %s after %d attempts: %s",
                            fn.__qualname__, max_retries + 1, exc,
                        )
                        raise RetryExhausted(max_retries + 1, exc) from exc

                    # Exponential backoff
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    if jitter:
                        delay *= random.uniform(0.5, 1.0)

                    logger.warning(
                        "Retry %d/%d for %s after %.2fs: %s",
                        attempt + 1, max_retries,
                        fn.__qualname__, delay, exc,
                    )
                    await asyncio.sleep(delay)

            # Should not reach here, but just in case
            raise RetryExhausted(max_retries + 1, last_exception)  # type: ignore[arg-type]

        return wrapper

    return decorator


class RetryWithBackoff:
    """Class-based retry with backoff for more control.

    Can be used as a context-managed retry loop::

        retry = RetryWithBackoff(max_retries=3, retry_on=(ConnectionError,))
        async for attempt in retry:
            async with attempt:
                result = await risky_call()

    Or use the ``execute`` method::

        result = await retry.execute(risky_call, arg1, arg2)
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        jitter: bool = True,
        retry_on: Tuple[Type[BaseException], ...] = (Exception,),
    ) -> None:
        self.config = RetryConfig(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            jitter=jitter,
            retry_on=retry_on,
        )

    async def execute(
        self,
        fn: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a callable with retry logic.

        Args:
            fn: Async callable to execute.
            *args: Positional arguments for fn.
            **kwargs: Keyword arguments for fn.

        Returns:
            The return value of fn on success.

        Raises:
            RetryExhausted: If all attempts fail.
        """
        cfg = self.config
        last_exception: Optional[BaseException] = None

        for attempt in range(cfg.max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except cfg.retry_on as exc:
                last_exception = exc
                if attempt == cfg.max_retries:
                    raise RetryExhausted(cfg.max_retries + 1, exc) from exc

                delay = min(cfg.base_delay * (2 ** attempt), cfg.max_delay)
                if cfg.jitter:
                    delay *= random.uniform(0.5, 1.0)

                logger.warning(
                    "Retry %d/%d for %s after %.2fs: %s",
                    attempt + 1, cfg.max_retries,
                    fn.__qualname__, delay, exc,
                )
                await asyncio.sleep(delay)

        raise RetryExhausted(cfg.max_retries + 1, last_exception)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ConnectionPool
# ---------------------------------------------------------------------------

@dataclass
class _PooledSession:
    """Internal wrapper around an aiohttp session with health metadata."""
    session: aiohttp.ClientSession
    created_at: float = field(default_factory=time.monotonic)
    last_used: float = field(default_factory=time.monotonic)
    healthy: bool = True
    request_count: int = 0


class ConnectionPool:
    """Managed pool of aiohttp sessions with health checks and auto-reconnect.

    Creates and maintains a pool of HTTP sessions to a base URL, with
    automatic health checking, timeout handling, and reconnection on failure.

    Args:
        base_url: Base URL for the service (used for health checks).
        pool_size: Number of sessions to maintain.
        timeout: Default request timeout in seconds.
        health_check_interval: Seconds between health checks for idle sessions.
        max_session_age: Maximum age of a session in seconds before recycling.
    """

    def __init__(
        self,
        base_url: str = "",
        pool_size: int = 3,
        timeout: float = 30.0,
        health_check_interval: float = 60.0,
        max_session_age: float = 300.0,
    ) -> None:
        self.base_url = base_url
        self.pool_size = pool_size
        self.timeout = timeout
        self.health_check_interval = health_check_interval
        self.max_session_age = max_session_age

        self._sessions: List[_PooledSession] = []
        self._lock = asyncio.Lock()
        self._started = False
        self._health_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Initialize the connection pool and start health checks."""
        if self._started:
            return

        async with self._lock:
            for _ in range(self.pool_size):
                self._sessions.append(await self._create_session())
            self._started = True

        self._health_task = asyncio.create_task(self._health_check_loop())
        logger.info(
            "ConnectionPool started: %d sessions for %s",
            self.pool_size, self.base_url or "(no base URL)",
        )

    async def stop(self) -> None:
        """Close all sessions and stop health checks."""
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None

        async with self._lock:
            for pooled in self._sessions:
                await self._close_session(pooled)
            self._sessions.clear()
            self._started = False

        logger.info("ConnectionPool stopped for %s", self.base_url or "(no base URL)")

    async def get_session(self) -> aiohttp.ClientSession:
        """Get a healthy session from the pool.

        Returns the least-recently-used healthy session. If no healthy
        sessions are available, creates a new one.

        Returns:
            An aiohttp.ClientSession ready for use.
        """
        async with self._lock:
            # Prefer healthy sessions, sorted by last_used (oldest first)
            healthy = [s for s in self._sessions if s.healthy]
            if healthy:
                chosen = min(healthy, key=lambda s: s.last_used)
                chosen.last_used = time.monotonic()
                chosen.request_count += 1
                return chosen.session

            # No healthy sessions -- recycle the oldest one
            logger.warning(
                "ConnectionPool: no healthy sessions, creating replacement"
            )
            new_session = await self._create_session()
            self._sessions.append(new_session)
            return new_session.session

    async def _create_session(self) -> _PooledSession:
        """Create a new pooled session."""
        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout),
            connector=aiohttp.TCPConnector(
                limit=10,
                enable_cleanup_closed=True,
            ),
        )
        return _PooledSession(session=session)

    async def _close_session(self, pooled: _PooledSession) -> None:
        """Safely close a pooled session."""
        try:
            if not pooled.session.closed:
                await pooled.session.close()
        except Exception as exc:
            logger.debug("Error closing session: %s", exc)

    async def _health_check_loop(self) -> None:
        """Periodic health check and session recycling."""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._run_health_checks()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.error("ConnectionPool health check error: %s", exc)

    async def _run_health_checks(self) -> None:
        """Check each session's health and recycle stale ones."""
        now = time.monotonic()
        async with self._lock:
            for i, pooled in enumerate(self._sessions):
                # Recycle old sessions
                age = now - pooled.created_at
                if age > self.max_session_age:
                    logger.debug(
                        "Recycling session %d (age=%.0fs)", i, age,
                    )
                    await self._close_session(pooled)
                    self._sessions[i] = await self._create_session()
                    continue

                # Check if session is closed
                if pooled.session.closed:
                    pooled.healthy = False
                    logger.debug("Session %d is closed, replacing", i)
                    self._sessions[i] = await self._create_session()
                    continue

                # Ping test if a base_url is configured
                if self.base_url:
                    try:
                        async with pooled.session.get(
                            self.base_url,
                            timeout=aiohttp.ClientTimeout(total=5.0),
                        ) as resp:
                            pooled.healthy = resp.status < 500
                    except Exception:
                        pooled.healthy = False
                        logger.debug("Session %d health check failed", i)

    @property
    def stats(self) -> Dict[str, Any]:
        """Pool statistics snapshot."""
        healthy_count = sum(1 for s in self._sessions if s.healthy)
        total_requests = sum(s.request_count for s in self._sessions)
        return {
            "total_sessions": len(self._sessions),
            "healthy_sessions": healthy_count,
            "total_requests": total_requests,
            "started": self._started,
        }


# ---------------------------------------------------------------------------
# HealthMonitor
# ---------------------------------------------------------------------------

@dataclass
class ServiceHealth:
    """Health status for a single registered service."""
    name: str
    healthy: bool = True
    last_check: float = 0.0
    last_latency_ms: float = 0.0
    consecutive_failures: int = 0
    last_error: Optional[str] = None
    total_checks: int = 0
    total_failures: int = 0


class HealthMonitor:
    """Periodic health monitor for all external services.

    Register health-check callables for each service. The monitor runs
    them on a configurable interval and maintains a real-time status
    dashboard.

    Args:
        check_interval: Seconds between health check rounds.
        unhealthy_threshold: Consecutive failures before marking unhealthy.

    Example::

        monitor = HealthMonitor(check_interval=30.0)
        monitor.register_service("hyperliquid", hl.ping)
        monitor.register_service("defillama", defillama_ping)
        await monitor.start()
        ...
        report = await monitor.get_health_report()
        await monitor.stop()
    """

    def __init__(
        self,
        check_interval: float = 30.0,
        unhealthy_threshold: int = 3,
    ) -> None:
        self.check_interval = check_interval
        self.unhealthy_threshold = unhealthy_threshold

        self._services: Dict[str, Callable[..., Awaitable[Any]]] = {}
        self._health: Dict[str, ServiceHealth] = {}
        self._task: Optional[asyncio.Task] = None
        self._started = False

    def register_service(
        self,
        name: str,
        health_check_fn: Callable[..., Awaitable[Any]],
    ) -> None:
        """Register a service for health monitoring.

        Args:
            name: Service name (e.g. "hyperliquid", "defillama", "etherscan").
            health_check_fn: An async callable that returns a truthy value on
                             success or raises on failure. If it returns a
                             float, it is interpreted as latency in ms.
        """
        self._services[name] = health_check_fn
        self._health[name] = ServiceHealth(name=name)
        logger.info("HealthMonitor: registered service '%s'", name)

    def unregister_service(self, name: str) -> None:
        """Remove a service from health monitoring."""
        self._services.pop(name, None)
        self._health.pop(name, None)

    async def start(self) -> None:
        """Start the periodic health check loop."""
        if self._started:
            return
        self._started = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info(
            "HealthMonitor started: %d services, interval=%.0fs",
            len(self._services), self.check_interval,
        )

    async def stop(self) -> None:
        """Stop the health check loop."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._started = False
        logger.info("HealthMonitor stopped")

    async def check_service(self, name: str) -> ServiceHealth:
        """Run a single health check for a named service.

        Args:
            name: The registered service name.

        Returns:
            Updated ServiceHealth for the service.

        Raises:
            KeyError: If the service is not registered.
        """
        if name not in self._services:
            raise KeyError(f"Service '{name}' is not registered")

        health = self._health[name]
        check_fn = self._services[name]
        start = time.monotonic()

        try:
            result = await asyncio.wait_for(check_fn(), timeout=10.0)
            elapsed_ms = (time.monotonic() - start) * 1000

            # If the check function returns a float, treat it as latency
            if isinstance(result, (int, float)):
                # Negative latency (e.g. from ping()) means failure
                if result < 0:
                    raise RuntimeError(f"Health check returned negative: {result}")
                elapsed_ms = float(result)

            health.healthy = True
            health.last_latency_ms = elapsed_ms
            health.consecutive_failures = 0
            health.last_error = None

        except Exception as exc:
            health.consecutive_failures += 1
            health.total_failures += 1
            health.last_error = str(exc)
            if health.consecutive_failures >= self.unhealthy_threshold:
                health.healthy = False
                logger.warning(
                    "HealthMonitor: '%s' marked UNHEALTHY "
                    "(%d consecutive failures): %s",
                    name, health.consecutive_failures, exc,
                )

        health.last_check = time.time()
        health.total_checks += 1
        return health

    async def check_all(self) -> Dict[str, ServiceHealth]:
        """Run health checks on all registered services concurrently.

        Returns:
            Dict mapping service name to its updated health status.
        """
        tasks = {
            name: asyncio.create_task(self.check_service(name))
            for name in self._services
        }
        results: Dict[str, ServiceHealth] = {}
        for name, task in tasks.items():
            try:
                results[name] = await task
            except Exception as exc:
                logger.error("Health check task error for '%s': %s", name, exc)
                results[name] = self._health[name]
        return results

    async def get_health_report(self) -> Dict[str, Any]:
        """Get a summary health report for all services.

        Returns:
            Dict with overall status and per-service details::

                {
                    "overall_healthy": True,
                    "services": {
                        "hyperliquid": {
                            "healthy": True,
                            "latency_ms": 42.3,
                            "consecutive_failures": 0,
                            ...
                        },
                        ...
                    },
                    "timestamp": 1711700000.0,
                }
        """
        report: Dict[str, Any] = {
            "overall_healthy": True,
            "services": {},
            "timestamp": time.time(),
        }

        for name, health in self._health.items():
            service_info = {
                "healthy": health.healthy,
                "latency_ms": round(health.last_latency_ms, 2),
                "consecutive_failures": health.consecutive_failures,
                "total_checks": health.total_checks,
                "total_failures": health.total_failures,
                "last_check": health.last_check,
                "last_error": health.last_error,
            }
            report["services"][name] = service_info
            if not health.healthy:
                report["overall_healthy"] = False

        return report

    async def _check_loop(self) -> None:
        """Periodic check loop running in the background."""
        while True:
            try:
                await asyncio.sleep(self.check_interval)
                await self.check_all()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.error("HealthMonitor check loop error: %s", exc)

    @property
    def is_healthy(self) -> bool:
        """True if all registered services are healthy."""
        return all(h.healthy for h in self._health.values())
