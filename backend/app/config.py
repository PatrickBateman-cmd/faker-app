from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    auth_enabled: bool = False
    secret_key: str = "dev"
    cors_origins: str = "http://localhost:5173"

    duckdb_path: str = "./duckdb"

    jwt_secret: str = "change-me"
    jwt_expiry_hours: int = 24

    yfinance_cache_ttl_quotes: int = 30
    yfinance_cache_ttl_historical: int = 3600

    iso20022_cache_ttl: int = 3600

    max_rows_per_dataset: int = 100000
    max_datasets_per_run: int = 4

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent.parent / ".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
