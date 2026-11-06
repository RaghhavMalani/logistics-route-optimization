"""Environment settings shared by the API, jobs and provider adapters."""

from functools import lru_cache
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Keep source values as strings for each domain's existing parsing rules."""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        extra="ignore",
        frozen=True,
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
    )

    AISSTREAM_API_KEY: str | None = Field(default=None, repr=False, exclude=True)
    DATABASE_URL: str | None = Field(default=None, repr=False, exclude=True)
    DATA_GOV_IN_API_KEY: str | None = Field(default=None, repr=False, exclude=True)
    DATA_GOV_IN_PORT_RESOURCE_ID: str | None = None
    EIA_API_KEY: str | None = Field(default=None, repr=False, exclude=True)
    KAFKA_BOOTSTRAP_SERVERS: str | None = Field(default=None, repr=False, exclude=True)
    OCEANS_X_API_KEY: str | None = Field(default=None, repr=False, exclude=True)
    OPEN_METEO_API_KEY: str | None = Field(default=None, repr=False, exclude=True)
    PORTWATCH_AIS_BOUNDING_BOXES: str | None = None
    PORTWATCH_AIS_RECORD_PATH: str | None = None
    PORTWATCH_AIS_REPLAY_PATH: str | None = None
    PORTWATCH_AIS_PUBLICATION_APPROVED: str | None = None
    PORTWATCH_AUTH_DB: str | None = None
    PORTWATCH_CHOKEPOINTS_URL: str | None = None
    PORTWATCH_CORS_REGEX: str | None = None
    PORTWATCH_CURRENT_ENVIRONMENT_DIR: str | None = None
    PORTWATCH_CURRENT_WEATHER_AUTOREFRESH: str | None = None
    PORTWATCH_DATA_DIR: str | None = None
    PORTWATCH_CACHE_DIR: str | None = None
    PORTWATCH_OUTPUTS_DIR: str | None = None
    PORTWATCH_EXPERIMENT_DIR: str | None = None
    PORTWATCH_FLEET_PROVIDER: str | None = None
    PORTWATCH_FREE_SOURCE_DIR: str | None = None
    PORTWATCH_FRESHNESS_SCHEDULER: str | None = None
    PORTWATCH_IDENTITY_MODE: str | None = None
    PORTWATCH_INTELLIGENCE_RECONCILIATION: str | None = None
    PORTWATCH_LICENCE_MODE: str | None = None
    PORTWATCH_LOCAL_PROVIDER_PROFILE: str | None = None
    PORTWATCH_MODEL: str | None = None
    PORTWATCH_NHO_ENABLED: str | None = None
    PORTWATCH_PANEL_SNAPSHOT_AT: str | None = None
    PORTWATCH_PIPELINE_AUTOREFRESH: str | None = None
    PORTWATCH_PUBLIC_CASE_DIR: str | None = None
    PORTWATCH_PUBLIC_EVIDENCE_SEED_MANIFEST: str | None = None
    PORTWATCH_PUBLIC_FEEDBACK_DB: str | None = None
    PORTWATCH_PUBLIC_PORT_AUTOREFRESH: str | None = None
    PORTWATCH_PUBLIC_RESEARCH_DIR: str | None = None
    PORTWATCH_PUBLIC_TARIFFS: str | None = None
    PORTWATCH_RELEASE_ENVIRONMENT: str | None = None
    PORTWATCH_RELEASE_SHA: str | None = None
    PORTWATCH_REQUIRE_RELEASE_MANIFEST: str | None = None
    PORTWATCH_RESEARCH_SOURCE_PROFILE: str | None = None
    PORTWATCH_SEA_ROUTES: str | None = None
    PORTWATCH_SOURCE: str | None = None
    PORTWATCH_SOURCE_SNAPSHOT_URL: str | None = Field(default=None, repr=False, exclude=True)
    PORTWATCH_STATE_DIR: str | None = None
    PORTWATCH_VESSELFINDER_ENABLED: str | None = None
    PORTWATCH_WEATHER_FEEDBACK_DB: str | None = None
    PORTWATCH_WEATHER_FEEDBACK_REPORT: str | None = None
    PORTWATCH_WEATHER_RECONCILIATION: str | None = None
    RAILWAY_DEPLOYMENT_ID: str | None = None
    RAILWAY_ENVIRONMENT_ID: str | None = None
    RAILWAY_SERVICE_ID: str | None = None
    VESSELFINDER_API_KEY: str | None = Field(default=None, repr=False, exclude=True)


    def get(self, name: str, default=None):
        value = getattr(self, name)
        return default if value is None else value

    def __getitem__(self, name: str) -> str:
        value = self.get(name)
        if value is None:
            raise KeyError(name)
        return value


_ENV_NAMES = tuple(Settings.model_fields)


@lru_cache(maxsize=16)
def _load(values: tuple[str | None, ...]) -> Settings:
    return Settings(**{name: value for name, value in zip(_ENV_NAMES, values) if value is not None})


def get_settings() -> Settings:
    """Reuse the validated object until a supported process variable changes."""
    return _load(tuple(os.environ.get(name) for name in _ENV_NAMES))
