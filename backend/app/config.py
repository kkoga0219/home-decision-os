"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Home Decision OS"
    debug: bool = False

    # Database
    database_url: str = "postgresql://hdos:hdos@localhost:5432/hdos"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # External APIs
    mlit_api_key: str = ""  # 不動産情報ライブラリ API key

    model_config = {"env_prefix": "HDOS_"}


settings = Settings()
