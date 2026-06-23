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

    # LINE Messaging API (for new-listing alerts)
    # NOTE: LINE Notify was discontinued on 2025-03-31; this uses the
    # LINE Messaging API (official account). Set the channel access token
    # and the push target (a userId / groupId / roomId). If the target is
    # left blank, the connector falls back to broadcast.
    line_channel_token: str = ""  # HDOS_LINE_CHANNEL_TOKEN
    line_target_id: str = ""  # HDOS_LINE_TARGET_ID (userId/groupId/roomId)

    # New-listing alert: where to persist the set of already-seen listings
    # so that only genuinely new properties trigger a notification.
    alert_state_path: str = ".alert_state/tsukaguchi_seen.json"

    # Render listing pages with a headless browser (Playwright) to defeat
    # SUUMO / athome anti-bot gates. Ignored gracefully if Playwright is not
    # installed. Disable with HDOS_ALERT_USE_BROWSER=false.
    alert_use_browser: bool = True

    model_config = {"env_prefix": "HDOS_"}


settings = Settings()
