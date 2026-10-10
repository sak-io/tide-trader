from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        # Explicit, so .env is read the same way everywhere - Windows' default locale
        # encoding (e.g. cp1252) would otherwise be used there.
        env_file_encoding="utf-8",
        extra="ignore",
    )

    alpaca_paper: bool = True

    max_position_dollars: float = 5000.0
    daily_loss_limit_pct: float = 0.03

    host: str = "127.0.0.1"
    port: int = 8000
    allowed_origins: str = ""

    db_path: str = "./tide_trader_state.db"

    scan_interval_seconds: int = 300
    scan_min_score: float = 60.0
    scan_most_active_top: int = 10
    scan_movers_top: int = 10
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-5-5"
    enable_suggestion_scanner: bool = True

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
