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

    # Minimum number of rooms for the alert (3 → 3LDK 以上).
    alert_min_rooms: int = 3

    # Exclude mansions built before this year (houses are exempt).
    # 1981 → keeps 新耐震基準 (1981-) and drops older mansions. 0 disables.
    alert_mansion_min_built_year: int = 1981

    # My-list watcher: file (committed) of URLs to track for price /
    # availability changes, and where to persist their snapshots.
    mylist_path: str = "mylist.txt"
    mylist_snapshots_path: str = ".alert_state/mylist_snapshots.json"

    # Optional HTTP(S) proxy for scraping. Anti-bot systems (esp. athome's
    # Imperva gate) often block datacenter IPs such as GitHub Actions
    # runners; routing through a residential proxy avoids that. Applied to
    # both httpx and the Playwright browser. Empty = direct connection.
    scrape_proxy: str = ""  # e.g. http://user:pass@host:port

    model_config = {"env_prefix": "HDOS_"}


settings = Settings()
