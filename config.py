"""Application settings, loaded from environment variables (12-factor style).

Every credential is read from the environment (or a local, git-ignored `.env`
file). Nothing secret is ever hardcoded.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["gemini", "groq", "deepseek", "openrouter"]


@dataclass(frozen=True)
class ProviderPreset:
    """Sensible per-provider defaults. All of them speak the OpenAI chat-completions protocol."""

    base_url: str
    default_model: str | None
    context_char_budget: int
    max_output_tokens: int
    reasoning_effort: str | None


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    # Gemini Flash: free tier + very large context window -> generous code budget.
    "gemini": ProviderPreset(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        default_model="gemini-2.5-flash",
        context_char_budget=160_000,
        max_output_tokens=16_384,
        reasoning_effort="low",
    ),
    # Groq free tier has low tokens-per-minute limits -> keep requests small.
    "groq": ProviderPreset(
        base_url="https://api.groq.com/openai/v1",
        default_model="openai/gpt-oss-120b",
        context_char_budget=24_000,
        max_output_tokens=8_192,
        reasoning_effort="low",
    ),
    "deepseek": ProviderPreset(
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        context_char_budget=120_000,
        max_output_tokens=8_000,
        reasoning_effort=None,
    ),
    # OpenRouter's free model list changes often, so the model must be set explicitly.
    "openrouter": ProviderPreset(
        base_url="https://openrouter.ai/api/v1",
        default_model=None,
        context_char_budget=60_000,
        max_output_tokens=8_192,
        reasoning_effort=None,
    ),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App -------------------------------------------------------------------------------
    app_env: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    # Optional shared secret. When set, every /audits endpoint requires `X-API-Key`.
    api_key: SecretStr | None = None

    # --- Database --------------------------------------------------------------------------
    db_backend: Literal["supabase", "memory"] = "supabase"
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None

    # --- LLM -------------------------------------------------------------------------------
    llm_provider: LLMProvider = "gemini"
    llm_api_key: SecretStr
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_context_char_budget: int | None = None
    llm_max_output_tokens: int | None = None
    llm_reasoning_effort: Literal["none", "low", "medium", "high"] | None = None
    llm_temperature: float = 0.1
    llm_timeout_seconds: float = 180.0
    llm_max_retries: int = 4

    # --- Ingestion limits ------------------------------------------------------------------
    github_token: SecretStr | None = None
    max_archive_mb: int = 40
    max_file_kb: int = 256
    max_files: int = 4_000
    max_total_uncompressed_mb: int = 150

    # --- Job execution ---------------------------------------------------------------------
    max_concurrent_audits: int = 2
    stale_audit_minutes: int = 20

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        if self.db_backend == "supabase" and (not self.supabase_url or not self.supabase_service_role_key):
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required when DB_BACKEND=supabase "
                "(set DB_BACKEND=memory for a quick local demo without Supabase)."
            )
        if not self.llm_model and self.preset.default_model is None:
            raise ValueError(f"LLM_MODEL must be set when LLM_PROVIDER={self.llm_provider}.")
        return self

    # --- Derived values --------------------------------------------------------------------
    @property
    def preset(self) -> ProviderPreset:
        return PROVIDER_PRESETS[self.llm_provider]

    @property
    def effective_llm_model(self) -> str:
        return self.llm_model or self.preset.default_model or ""

    @property
    def effective_llm_base_url(self) -> str:
        return (self.llm_base_url or self.preset.base_url).rstrip("/")

    @property
    def effective_context_budget(self) -> int:
        return self.llm_context_char_budget or self.preset.context_char_budget

    @property
    def effective_max_output_tokens(self) -> int:
        return self.llm_max_output_tokens or self.preset.max_output_tokens

    @property
    def effective_reasoning_effort(self) -> str | None:
        if self.llm_reasoning_effort == "none":
            return None
        return self.llm_reasoning_effort or self.preset.reasoning_effort

    @property
    def max_archive_bytes(self) -> int:
        return self.max_archive_mb * 1024 * 1024

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_kb * 1024

    @property
    def max_total_uncompressed_bytes(self) -> int:
        return self.max_total_uncompressed_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  (values come from the environment)
