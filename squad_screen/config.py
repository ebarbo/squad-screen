from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    football_data_api_key: str = ""
    api_football_key: str = ""
    thesportsdb_api_key: str = "123"

    newsapi_key: str = ""
    guardian_api_key: str = ""
    gnews_api_key: str = ""

    twitter_bearer_token: str = ""

    # Instagram Graph API Business Discovery (v1.1). Auto-used when token + IG user id are set.
    instagram_access_token: str = ""
    instagram_business_account_id: str = ""
    instagram_enabled: bool = True
    instagram_graph_version: str = "v21.0"
    instagram_max_players: int = 20
    instagram_max_media: int = 10
    instagram_handles_file: str = "config/instagram_handles.json"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    http_user_agent: str = (
        "SquadScreen/0.1 (+https://github.com; match-day readiness research)"
    )
    http_timeout_seconds: float = 20.0
    news_concurrency: int = 4

    lookback_days: int = 3
    report_dir: str = "reports"

    @property
    def instagram_ready(self) -> bool:
        """True when live Instagram Business Discovery should run."""
        return bool(
            self.instagram_enabled
            and self.instagram_access_token.strip()
            and self.instagram_business_account_id.strip()
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
