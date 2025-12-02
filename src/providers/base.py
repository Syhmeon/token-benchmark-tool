"""Base classes for data providers."""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from ..core.models import AuditEntry
from ..core.types import DataSource

logger = logging.getLogger(__name__)


class BaseProvider(ABC):
    """Abstract base class for all data providers."""

    # Subclasses must define their data source
    SOURCE: DataSource = DataSource.UNKNOWN

    def __init__(
        self,
        rate_limit_calls: int = 60,
        rate_limit_period: int = 60,
    ):
        """
        Initialize provider with rate limiting.

        Args:
            rate_limit_calls: Maximum calls per period
            rate_limit_period: Period in seconds
        """
        self.rate_limit_calls = rate_limit_calls
        self.rate_limit_period = rate_limit_period
        self._call_timestamps: list[float] = []
        self._audit_entries: list[AuditEntry] = []

    def _wait_for_rate_limit(self) -> None:
        """Enforce rate limiting by sleeping if necessary."""
        now = time.time()
        # Clean old timestamps
        self._call_timestamps = [
            ts for ts in self._call_timestamps if now - ts < self.rate_limit_period
        ]

        if len(self._call_timestamps) >= self.rate_limit_calls:
            sleep_time = self._call_timestamps[0] + self.rate_limit_period - now
            if sleep_time > 0:
                logger.debug(
                    f"[{self.SOURCE.value}] Rate limit: sleeping {sleep_time:.1f}s"
                )
                time.sleep(sleep_time)

        self._call_timestamps.append(time.time())

    def _record_audit(
        self,
        action: str,
        endpoint: str | None = None,
        success: bool = True,
        error_message: str | None = None,
        duration_ms: int | None = None,
        notes: str | None = None,
    ) -> AuditEntry:
        """Record an audit entry for this provider action."""
        entry = AuditEntry(
            timestamp=datetime.utcnow(),
            source=self.SOURCE,
            action=action,
            endpoint=endpoint,
            success=success,
            error_message=error_message,
            duration_ms=duration_ms,
            notes=notes,
        )
        self._audit_entries.append(entry)
        return entry

    def get_audit_trail(self) -> list[AuditEntry]:
        """Return all audit entries recorded by this provider."""
        return self._audit_entries.copy()

    def clear_audit_trail(self) -> None:
        """Clear the audit trail."""
        self._audit_entries.clear()

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available and configured."""
        pass


class CachedProvider(BaseProvider):
    """Base class for providers with caching support."""

    def __init__(
        self,
        cache_ttl_seconds: int = 3600,
        **kwargs: Any,
    ):
        """
        Initialize cached provider.

        Args:
            cache_ttl_seconds: Cache time-to-live in seconds
            **kwargs: Passed to BaseProvider
        """
        super().__init__(**kwargs)
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[Any, float]] = {}

    def _get_from_cache(self, key: str) -> Any | None:
        """Get value from cache if not expired."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self.cache_ttl_seconds:
                logger.debug(f"[{self.SOURCE.value}] Cache hit: {key}")
                return value
            else:
                del self._cache[key]
        return None

    def _set_cache(self, key: str, value: Any) -> None:
        """Store value in cache."""
        self._cache[key] = (value, time.time())

    def clear_cache(self) -> None:
        """Clear the cache."""
        self._cache.clear()
