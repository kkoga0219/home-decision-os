"""New-listing alert for the 塚口 (Tsukaguchi) area.

Pipeline:
  1. Search SUUMO / HOME'S / athome for 中古マンション and 中古戸建て
     around 塚口 (兵庫県尼崎市).
  2. Keep only listings that satisfy the walk-distance rule
     (see ``tsukaguchi_filter``):
        - 阪急塚口 within 10 min, OR
        - JR塚口 AND 阪急塚口 both within 15 min.
  3. Drop listings already seen on a previous run (``AlertState``).
  4. Push the new ones to LINE (``LineNotifyConnector``).

Exposed as both an API endpoint and a standalone script so it can be run
on a schedule (e.g. a GitHub Actions cron workflow).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.connectors.athome_search import AthomeSearchConnector
from app.connectors.homes_search import HomesSearchConnector
from app.connectors.line_notify import LineNotifyConnector
from app.connectors.suumo_search import SuumoSearchConnector
from app.services.alert_state import AlertState, listing_key
from app.services.tsukaguchi_filter import evaluate_access, layout_meets_minimum

logger = logging.getLogger(__name__)

# Search location for the 塚口 area.
# Both 塚口 stations (阪急・JR) sit in 尼崎市, so we search the city and let
# the walk-distance filter narrow results to genuinely 塚口-adjacent listings.
# (SUUMO resolves the station-level URL directly from station_name; HOME'S /
# athome fall back to the 尼崎市 list page, which is far more reliable than
# their free-text keyword search.)
_STATION = "塚口"
_CITY = "尼崎市"
_PREFECTURE = "兵庫県"

# Property types to monitor.
_PROPERTY_TYPES = ("mansion", "house")
_TYPE_LABEL = {"mansion": "中古マンション", "house": "中古戸建て"}

# Safety cap so a first run (everything is "new") cannot spam LINE.
_MAX_NOTIFY = 30


async def gather_candidates(
    *,
    sources: list[str] | None = None,
    max_pages: int = 1,
    assume_unknown_is_hankyu: bool = True,
    use_browser: bool = True,
    min_rooms: int = 3,
) -> list[dict[str, Any]]:
    """Search all sources/types and return qualifying listings.

    The returned listings are de-duplicated by listing key and annotated
    with ``source``, ``property_type``, ``property_type_label`` and
    ``match_reason``. No state / notification side effects.

    ``use_browser`` enables the Playwright fallback for SUUMO / athome (see
    ``browser_fetch``); it is ignored gracefully if Playwright is not
    installed. ``min_rooms`` filters by layout (3 → 3LDK 以上).
    """
    srcs = [s.lower() for s in (sources or ["suumo", "homes", "athome"])]

    async def _one(connector, ptype: str):
        return ptype, await connector.fetch(
            station_name=_STATION,
            city_name=_CITY,
            prefecture=_PREFECTURE,
            max_pages=max_pages,
            property_type=ptype,
            use_browser=use_browser,
        )

    tasks = []
    for ptype in _PROPERTY_TYPES:
        if "suumo" in srcs:
            tasks.append(_one(SuumoSearchConnector(), ptype))
        if "homes" in srcs:
            tasks.append(_one(HomesSearchConnector(), ptype))
        if "athome" in srcs:
            tasks.append(_one(AthomeSearchConnector(), ptype))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    qualifying: dict[str, dict[str, Any]] = {}
    for res in results:
        if isinstance(res, Exception):
            logger.warning("alert search task failed: %s", res)
            continue
        ptype, result = res
        if not getattr(result, "success", False):
            continue
        for listing in result.data.get("listings", []):
            verdict = evaluate_access(
                listing.get("access", ""),
                assume_unknown_is_hankyu=assume_unknown_is_hankyu,
            )
            if not verdict.qualifies:
                continue
            if not layout_meets_minimum(listing.get("layout", ""), min_rooms):
                continue
            listing.setdefault("source", _source_of(result))
            listing["property_type"] = ptype
            listing["property_type_label"] = _TYPE_LABEL[ptype]
            listing["match_reason"] = verdict.reason
            qualifying[listing_key(listing)] = listing

    return list(qualifying.values())


def _source_of(result: Any) -> str:
    name = (getattr(result, "source", "") or "").lower()
    if "suumo" in name:
        return "suumo"
    if "home" in name:
        return "homes"
    if "athome" in name:
        return "athome"
    return name or "?"


async def run_tsukaguchi_alert(
    *,
    channel_token: str,
    target_id: str = "",
    state_path: str,
    sources: list[str] | None = None,
    max_pages: int = 1,
    assume_unknown_is_hankyu: bool = True,
    use_browser: bool = True,
    min_rooms: int = 3,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the full alert pipeline and (optionally) push to LINE.

    Returns a summary dict suitable for an API response or CLI log.
    """
    candidates = await gather_candidates(
        sources=sources,
        max_pages=max_pages,
        assume_unknown_is_hankyu=assume_unknown_is_hankyu,
        use_browser=use_browser,
        min_rooms=min_rooms,
    )

    state = AlertState.load(state_path)
    new_listings = [ls for ls in candidates if state.is_new(ls)]

    notify = new_listings[:_MAX_NOTIFY]
    truncated = len(new_listings) - len(notify)

    errors: list[str] = []
    sent = 0
    if notify and not dry_run:
        messages = build_messages(notify, truncated=truncated)
        connector = LineNotifyConnector(
            channel_token=channel_token,
            target_id=target_id,
        )
        line_result = await connector.fetch(messages=messages)
        sent = line_result.data.get("sent", 0)
        errors.extend(line_result.errors)
        # Only remember listings we actually attempted to notify about,
        # so a send failure can be retried on the next run.
        if line_result.success:
            for ls in notify:
                state.mark(ls)
            state.save(state_path)
    elif notify and dry_run:
        for ls in notify:
            state.mark(ls)
        # In dry-run we still persist so repeated dry-runs are quiet.
        state.save(state_path)

    return {
        "candidates": len(candidates),
        "new": len(new_listings),
        "notified": len(notify),
        "truncated": truncated,
        "sent": sent,
        "dry_run": dry_run,
        "seen_total": len(state),
        "errors": errors,
        "listings": notify,
    }


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------

_LISTINGS_PER_MESSAGE = 5


def _format_listing(ls: dict[str, Any]) -> str:
    label = ls.get("property_type_label", "")
    name = ls.get("name", "(物件名不明)")
    lines = [f"🏠 {label}｜{name}"]
    price = ls.get("price_text") or (
        f"{ls['price_jpy'] // 10_000:,}万円" if ls.get("price_jpy") else ""
    )
    if price:
        lines.append(f"💰 {price}")
    if ls.get("match_reason"):
        lines.append(f"🚉 {ls['match_reason']}")
    if ls.get("address"):
        lines.append(f"📍 {ls['address']}")
    if ls.get("url"):
        lines.append(f"🔗 {ls['url']}")
    return "\n".join(lines)


def build_messages(
    listings: list[dict[str, Any]],
    *,
    truncated: int = 0,
) -> list[str]:
    """Format qualifying listings into LINE text messages."""
    if not listings:
        return []

    blocks = [_format_listing(ls) for ls in listings]
    header = f"🆕 塚口エリア 新着物件 {len(listings)}件"

    messages: list[str] = []
    for i in range(0, len(blocks), _LISTINGS_PER_MESSAGE):
        chunk = blocks[i : i + _LISTINGS_PER_MESSAGE]
        prefix = header if i == 0 else "（続き）"
        messages.append(prefix + "\n\n" + "\n\n".join(chunk))

    if truncated > 0:
        messages.append(f"ほか {truncated} 件は次回以降に通知します。")

    return messages
