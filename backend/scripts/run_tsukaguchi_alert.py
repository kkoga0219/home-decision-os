#!/usr/bin/env python3
"""Run the 塚口 new-listing LINE alert (for cron / GitHub Actions).

Reads configuration from the same environment variables as the backend:

    HDOS_LINE_CHANNEL_TOKEN   LINE Messaging API channel access token (required)
    HDOS_LINE_TARGET_ID       push target userId/groupId/roomId (optional;
                              blank → broadcast to all friends)
    HDOS_ALERT_STATE_PATH     where to persist the "already seen" set
                              (default: .alert_state/tsukaguchi_seen.json)

Usage:
    python scripts/run_tsukaguchi_alert.py             # search + notify
    python scripts/run_tsukaguchi_alert.py --dry-run   # preview, no LINE send
    python scripts/run_tsukaguchi_alert.py --max-pages 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from app.config import settings
from app.services.listing_alert import run_tsukaguchi_alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("tsukaguchi_alert")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="塚口エリア 新着物件 LINE通知")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="LINE送信せず、対象物件の判定だけ行う",
    )
    p.add_argument(
        "--max-pages",
        type=int,
        default=1,
        help="各サイトで取得する検索結果ページ数 (default: 1)",
    )
    p.add_argument(
        "--sources",
        default="suumo,homes,athome",
        help="カンマ区切りの検索ソース (default: suumo,homes,athome)",
    )
    return p.parse_args(argv)


async def _main(argv: list[str]) -> int:
    args = _parse_args(argv)
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    if not args.dry_run and not settings.line_channel_token:
        logger.error(
            "HDOS_LINE_CHANNEL_TOKEN が未設定です。"
            "--dry-run で動作確認するか、トークンを設定してください。"
        )
        return 2

    summary = await run_tsukaguchi_alert(
        channel_token=settings.line_channel_token,
        target_id=settings.line_target_id,
        state_path=settings.alert_state_path,
        sources=sources,
        max_pages=args.max_pages,
        dry_run=args.dry_run,
    )

    # Don't dump full listing bodies into the log line.
    log_summary = {k: v for k, v in summary.items() if k != "listings"}
    logger.info("結果: %s", json.dumps(log_summary, ensure_ascii=False))

    if summary["errors"]:
        for err in summary["errors"]:
            logger.error("error: %s", err)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main(sys.argv[1:])))
