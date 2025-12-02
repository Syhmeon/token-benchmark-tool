"""Custom exceptions for the token listing tool."""


class TokenListingError(Exception):
    """Base exception for all token listing tool errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class TokenNotFoundError(TokenListingError):
    """Raised when a token cannot be found in any data source."""

    def __init__(self, token_identifier: str, sources_checked: list[str] | None = None):
        message = f"Token not found: {token_identifier}"
        if sources_checked:
            message += f" (checked: {', '.join(sources_checked)})"
        super().__init__(message, {"token": token_identifier, "sources": sources_checked})
        self.token_identifier = token_identifier
        self.sources_checked = sources_checked or []


class DataSourceError(TokenListingError):
    """Raised when a data source fails or returns invalid data."""

    def __init__(
        self,
        source: str,
        message: str,
        endpoint: str | None = None,
        status_code: int | None = None,
    ):
        full_message = f"[{source}] {message}"
        super().__init__(
            full_message,
            {
                "source": source,
                "endpoint": endpoint,
                "status_code": status_code,
            },
        )
        self.source = source
        self.endpoint = endpoint
        self.status_code = status_code


class RateLimitError(DataSourceError):
    """Raised when API rate limit is hit."""

    def __init__(
        self,
        source: str,
        retry_after_seconds: int | None = None,
        endpoint: str | None = None,
    ):
        message = "Rate limit exceeded"
        if retry_after_seconds:
            message += f", retry after {retry_after_seconds}s"
        super().__init__(source, message, endpoint=endpoint, status_code=429)
        self.retry_after_seconds = retry_after_seconds


class ValidationError(TokenListingError):
    """Raised when data validation fails."""

    def __init__(self, field: str, value: str, reason: str):
        message = f"Validation failed for {field}={value}: {reason}"
        super().__init__(message, {"field": field, "value": value, "reason": reason})
        self.field = field
        self.value = value
        self.reason = reason


class ConfigurationError(TokenListingError):
    """Raised when configuration is invalid or missing."""

    def __init__(self, config_key: str, message: str):
        full_message = f"Configuration error [{config_key}]: {message}"
        super().__init__(full_message, {"config_key": config_key})
        self.config_key = config_key


class MappingError(TokenListingError):
    """Raised when allocation mapping fails."""

    def __init__(self, raw_label: str, message: str):
        full_message = f"Failed to map allocation '{raw_label}': {message}"
        super().__init__(full_message, {"raw_label": raw_label})
        self.raw_label = raw_label
