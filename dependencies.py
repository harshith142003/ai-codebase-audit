"""FastAPI dependencies (wired from app.state so tests can inject fakes)."""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from app.config import Settings
from app.services.audit_service import AuditService

# Declared as a security scheme so Swagger UI (/docs) shows an "Authorize" button.
api_key_header = APIKeyHeader(
    name="X-API-Key", auto_error=False, description="Required when the server is configured with API_KEY."
)


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_audit_service(request: Request) -> AuditService:
    return request.app.state.audit_service


async def require_api_key(request: Request, x_api_key: str | None = Security(api_key_header)) -> None:
    """If API_KEY is configured, require a matching X-API-Key header (protects the LLM quota)."""
    expected = request.app.state.settings.api_key
    if expected is None:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected.get_secret_value()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid X-API-Key header.")
