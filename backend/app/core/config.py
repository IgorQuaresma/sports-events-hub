"""Application settings, loaded from environment variables / .env.

Secrets (API keys, tokens) live only here — never in `source.config` rows, which are
stored in the database and returned by admin endpoints.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SERVICE_TOKEN = "dev-service-token-change-me"
DEFAULT_CLICK_SALT = "dev-click-salt-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Sports Events Hub"
    environment: Literal["dev", "test", "staging", "prod"] = "dev"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/hub"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Where raw fetched documents are stored (S3 in production; local dir for the MVP)
    raw_dir: Path = Path("data/raw")

    # Fetcher politeness / safety
    fetcher_user_agent: str = (
        "SportsEventsHubBot/0.2 (+https://github.com/IgorQuaresma/sports-events-hub)"
    )
    fetch_timeout_s: float = 15.0
    fetch_max_bytes: int = 5_000_000
    fetch_min_delay_s: float = 1.0
    fetch_max_retries: int = 2

    # AI
    anthropic_api_key: SecretStr | None = None
    llm_model_fast: str = "claude-haiku-5-5"
    llm_model_extract: str = "claude-sonnet-5-5"

    # --- external data APIs (see docs/DATA_SOURCES.md) ---
    # World Triathlon: optional. Without a key the keyless public mirror is used.
    world_triathlon_api_key: SecretStr | None = None
    # Ticketmaster Discovery API (free key: https://developer.ticketmaster.com)
    ticketmaster_api_key: SecretStr | None = None
    # RunSignup: the public race search works without credentials.
    runsignup_api_key: SecretStr | None = None
    runsignup_api_secret: SecretStr | None = None

    # Enrichment
    # Nominatim geocoding for venues without coordinates. Off by default; when on, obey
    # https://operations.osmfoundation.org/policies/nominatim/ (1 req/s, cache, contact).
    geocoding_enabled: bool = False
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    # Open-Meteo race-day forecast (races in the next 16 days)
    weather_enabled: bool = True
    open_meteo_url: str = "https://api.open-meteo.com/v1/forecast"
    # Sent to Nominatim / Wikidata, whose usage policies ask for a contact
    contact_email: str | None = None

    # Service token for POST /v1/ingest/candidates and admin endpoints
    service_token: SecretStr = SecretStr(DEFAULT_SERVICE_TOKEN)
    # Secret salt for pseudonymous outbound-click hashing (combined with the date → daily rotation)
    click_hash_salt: SecretStr = SecretStr(DEFAULT_CLICK_SALT)

    # Abuse protection for the (potentially LLM-backed) query parser, per client IP
    parse_rate_limit_per_minute: int = 30

    public_base_url: str = "http://localhost:8000"
    public_web_url: str = "http://localhost:3000"

    @model_validator(mode="after")
    def _no_default_secrets_outside_dev(self) -> "Settings":
        if self.environment in ("staging", "prod"):
            if self.service_token.get_secret_value() == DEFAULT_SERVICE_TOKEN:
                raise ValueError("SERVICE_TOKEN must be set to a strong secret outside dev")
            if self.click_hash_salt.get_secret_value() == DEFAULT_CLICK_SALT:
                raise ValueError("CLICK_HASH_SALT must be set outside dev")
            if "*" in self.cors_origins:
                raise ValueError("CORS_ORIGINS must not contain '*' outside dev")
        return self

    @property
    def is_prod(self) -> bool:
        return self.environment == "prod"

    def secret(self, name: str) -> str | None:
        """Plain value of an optional secret setting, or None when unset or empty."""
        value = getattr(self, name)
        if value is None:
            return None
        plain = value.get_secret_value() if isinstance(value, SecretStr) else str(value)
        return plain or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
