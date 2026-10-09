"""Domain errors. Each carries the HTTP status the API layer should map it to."""

from __future__ import annotations


class AuditError(Exception):
    """Base class for expected, user-facing failures."""

    http_status: int = 500

    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if http_status is not None:
            self.http_status = http_status


class IngestError(AuditError):
    """Problems fetching or unpacking the source code (bad URL, private repo, bad ZIP, too large)."""

    http_status = 400


class LLMError(AuditError):
    """The LLM provider failed (network, rate limit, auth, server error)."""

    http_status = 502


class LLMOutputError(LLMError):
    """The LLM answered, but its output could not be validated against the schema."""


class NotFoundError(AuditError):
    http_status = 404
