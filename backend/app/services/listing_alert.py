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

import httpx

from app.connectors.athome_search import AthomeSearchConnector
from app.connectors.homes_search import HomesSearchConnector
from app.connectors.line_notify import LineNotifyConnector
from app.connectors.suumo_search import (
    HEADERS as _SUUMO_HEADERS,
)
from app.connectors.suumo_search import (
    SuumoSearchConnector,
    fetch_suumo_full_access,
)
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
    max_pages: int = 30,
    assume_unknown_is_hankyu: bool = False,
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

    # First pass: collect all candidates that pass the layout filter, then
    # for SUUMO listings whose list-card access doesn't already mention
    # 塚口/猪名寺, enrich `access` from the detail page (SUUMO list cards
    # show only one rep station, hiding e.g. "阪急塚口 徒歩14分").
    pending: list[tuple[str, dict[str, Any], Any]] = []
    for res in results:
        if isinstance(res, Exception):
            logger.warning("alert search task failed: %s", res)
            continue
        ptype, result = res
        if not getattr(result, "success", False):
            continue
        for listing in result.data.get("listings", []):
            if not layout_meets_minimum(listing.get("layout", ""), min_rooms):
                continue
            pending.append((ptype, listing, result))

    await _enrich_suumo_access(pending)

    qualifying: dict[str, dict[str, Any]] = {}
    for ptype, listing, result in pending:
        verdict = evaluate_access(
            listing.get("access", ""),
            assume_unknown_is_hankyu=assume_unknown_is_hankyu,
        )
        if not verdict.qualifies:
            continue
        listing.setdefault("source", _source_of(result))
        listing["property_type"] = ptype
        listing["property_type_label"] = _TYPE_LABEL[ptype]
        listing["match_reason"] = verdict.reason
        qualifying[listing_key(listing)] = listing

    return list(qualifying.values())


# Address-based trigger: 町 names within plausible walking distance of
# 阪急塚口 / JR塚口 / 猪名寺. If the LIST-CARD address contains any of
# these tokens, we fetch the detail page to get all rail accesses (the
# card only prints one rep station which often hides 塚口).
_ENRICH_ADDRESS_TOKENS = (
    "塚口本町",
    "南塚口町",
    "東塚口町",
    "北塚口町",
    "上坂部",
    "下坂部",
    "名神町",
    "南武庫之荘",
    "東難波町",
    "御園",
    "富松町",
    "久々知",
    "猪名寺",
    "若王寺",
    "戸ノ内町",
)
# Cap enrichments per run to keep us polite (and runtime bounded).
_MAX_SUUMO_ENRICH = 80


async def _enrich_suumo_access(
    pending: list[tuple[str, dict[str, Any], Any]],
) -> None:
    """For SUUMO listings whose list-card access hides 塚口/猪名寺 access,
    fetch the detail page and replace `access` with the full 交通 row.

    Triggered when the listing's ADDRESS sits in the 塚口 walking shed —
    those are the ones SUUMO most often mislabels with a non-塚口 rep
    station (e.g. 塚口本町6 listings tagged "猪名寺 徒歩11分" only).
    """
    from app.config import settings

    def _needs_enrich(ls: dict[str, Any]) -> bool:
        if not ls.get("url"):
            return False
        # Skip only if the list-card access ALREADY qualifies — the card
        # might mention 塚口/猪名寺 but only partially (e.g. just 猪名寺,
        # missing 阪急塚口), in which case we still need the detail page.
        if evaluate_access(ls.get("access", "")).qualifies:
            return False
        address = ls.get("address", "")
        return any(tok in address for tok in _ENRICH_ADDRESS_TOKENS)

    targets = [
        ls
        for (_ptype, ls, result) in pending
        if _source_of(result) == "suumo" and _needs_enrich(ls)
    ][:_MAX_SUUMO_ENRICH]
    if not targets:
        return
    logger.info("SUUMO enrichment: fetching %d detail pages", len(targets))

    sem = asyncio.Semaphore(4)

    async def _one(client: httpx.AsyncClient, ls: dict[str, Any]) -> None:
        async with sem:
            full = await fetch_suumo_full_access(client, ls["url"])
            if full:
                ls["access"] = full
                ls["access_method"] = "detail-page"

    try:
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            http2=False,
            headers=_SUUMO_HEADERS,
            proxy=settings.scrape_proxy or None,
        ) as client:
            await asyncio.gather(*[_one(client, ls) for ls in targets])
    except Exception as exc:  # noqa: BLE001 - non-fatal enrichment
        logger.info("SUUMO enrichment failed: %s", exc)


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
    max_pages: int = 30,
    assume_unknown_is_hankyu: bool = False,
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
