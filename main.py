"""FastAPI application factory.

`create_app()` wires concrete dependencies (Supabase, LLM provider, GitHub) in
the lifespan hook. Tests pass a pre-built `AuditService` with fakes instead.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app import __version__
from app.api import audits, health
from app.config import Settings, get_settings
from app.db.factory import build_repository
from app.errors import AuditError
from app.llm.client import OpenAICompatibleClient
from app.services.audit_service import AuditService
from app.services.github import GitHubClient

logger = logging.getLogger("app")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def create_app(settings: Settings | None = None, service: AuditService | None = None) -> FastAPI:
    settings = settings or get_settings()
    _configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        http: httpx.AsyncClient | None = None
        if service is not None:
            app.state.audit_service = service
        else:
            http = httpx.AsyncClient(headers={"User-Agent": f"ai-codebase-audit/{__version__}"})
            app.state.audit_service = AuditService(
                repository=build_repository(settings),
                llm=OpenAICompatibleClient.from_settings(settings, http),
                github=GitHubClient(settings, http),
                settings=settings,
            )
            await app.state.audit_service.recover_stale_runs()
        logger.info(
            "Started: db=%s llm=%s/%s", settings.db_backend, settings.llm_provider, settings.effective_llm_model
        )
        yield
        if http is not None:
            await http.aclose()

    app = FastAPI(
        title="AI Codebase Audit & Proposal Engine",
        version=__version__,
        description=(
            "Audits codebases produced by AI app builders (Lovable, v0, Bolt): extracts structure, runs "
            "deterministic checks plus a cost-effective LLM review, stores itemised findings in Supabase, and "
            "returns a client-ready Markdown report."
        ),
        lifespan=lifespan,
    )

    @app.exception_handler(AuditError)
    async def _audit_error_handler(_: Request, exc: AuditError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content={"detail": exc.message})

    @app.get("/", include_in_schema=False)
    async def _root() -> RedirectResponse:
        return RedirectResponse("/docs")

    app.include_router(health.router)
    app.include_router(audits.router)
    return app


app = create_app()
