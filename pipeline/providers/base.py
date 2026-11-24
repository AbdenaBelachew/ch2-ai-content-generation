"""Base provider interface and error handling with exponential backoff."""

from abc import ABC, abstractmethod
import time
from typing import Any, Callable, Dict, Optional, TypeVar

T = TypeVar("T")


class ProviderError(Exception):
    """Base exception for provider communication errors."""
    pass


class AuthenticationError(ProviderError):
    """Raised on authentication or permission failure (non-retryable)."""
    pass


class RateLimitError(ProviderError):
    """Raised on rate limits (retryable)."""
    pass


class TransientProviderError(ProviderError):
    """Raised on temporary provider network or server errors (retryable)."""
    pass


def retry_with_backoff(
    fn: Callable[..., T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple = (RateLimitError, TransientProviderError),
) -> T:
    """Execute a function with exponential backoff on transient errors.

    Permanent validation and authentication errors are not retried.
    """
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return fn()
        except AuthenticationError:
            # Do not retry auth errors indefinitely
            raise
        except retryable_exceptions as exc:
            last_exception = exc
            if attempt < max_retries:
                time.sleep(delay)
                delay *= backoff_factor
            else:
                break
        except Exception as exc:
            # Check for HTTP status codes if available
            status_code = getattr(exc, "status_code", None)
            if status_code in (401, 403):
                raise AuthenticationError(f"Authentication failed: {exc}") from exc
            if status_code in (429, 502, 503, 504):
                last_exception = exc
                if attempt < max_retries:
                    time.sleep(delay)
                    delay *= backoff_factor
                    continue
            raise

    raise ProviderError(f"Operation failed after {max_retries} retries: {last_exception}") from last_exception


class BaseProvider(ABC):
    """Abstract base class for all external AI model providers."""

    @abstractmethod
    def verify_connection(self) -> Dict[str, Any]:
        """Perform a minimal smoke test to check API availability.

        Returns a dictionary with status, message, and details.
        Never pretends a provider call succeeded when it has not.
        """
        pass

