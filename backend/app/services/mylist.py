"""My-list watcher: track specific properties for price/status changes.

How it works
============
- Users curate a list of property URLs in ``mylist.txt`` (one URL per line;
  blank lines and ``#`` comments allowed). The file is committed to the
  repo so it can be edited from GitHub's web UI.
- On every scheduled run, we fetch each URL's detail page and snapshot the
  current state (price, layout, address, status). Snapshots are persisted
  via ``actions/cache`` so the next run can diff.
- Whenever a property's snapshot differs from the previous one — price
  changed, layout changed, the listing went 成約済み / 404 — we push a
  LINE message describing the change.

Portal support
==============
Currently SUUMO (中古マンション + 中古戸建て) and athome are fully
implemented. HOME'S detail pages have a different structure and are
fetched but only their availability is tracked (price changes not parsed
yet).
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.connectors.athome_search import HEADERS as _ATHOME_HEADERS
from app.connectors.athome_search import _extract_bukken_list
from app.connectors.line_notify import LineNotifyConnector
from app.connectors.suumo_search import HEADERS as _SUUMO_HEADERS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Store: list (committed text file) + snapshots (cached JSON)
# ---------------------------------------------------------------------------


class MyListStore:
    """Read the user-curated URL list + persist per-URL snapshots."""

    def __init__(self, list_path: str | Path, snapshots_path: str | Path) -> None:
        self.list_path = Path(list_path)
        self.snapshots_path = Path(snapshots_path)

    def load_urls(self) -> list[str]:
        if not self.list_path.exists():
            return []
        urls: list[str] = []
        for raw in self.list_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)
        # De-dupe while preserving order.
        seen: set[str] = set()
        unique: list[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        return unique

    def load_snapshots(self) -> dict[str, dict[str, Any]]:
        if not self.snapshots_path.exists():
            return {}
        try:
            raw = json.loads(self.snapshots_path.read_text(encoding="utf-8"))
            return raw.get("snapshots", {}) if isinstance(raw, dict) else {}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "could not read mylist snapshots %s: %s",
                self.snapshots_path,
                exc,
            )
            return {}

    def save_snapshots(self, snapshots: dict[str, dict[str, Any]]) -> None:
        self.snapshots_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": _dt.datetime.now(_dt.UTC).isoformat(),
            "count": len(snapshots),
            "snapshots": snapshots,
        }
        self.snapshots_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Snapshot model + diff
# ---------------------------------------------------------------------------


@dataclass
class Snapshot:
    """Subset of listing fields tracked for change detection."""

    url: str
    status: str = "active"  # "active" | "sold" | "removed" | "unknown"
    name: str = ""
    price_jpy: int | None = None
    address: str = ""
    layout: str = ""
    access: str = ""
    fetched_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status": self.status,
            "name": self.name,
            "price_jpy": self.price_jpy,
            "address": self.address,
            "layout": self.layout,
            "access": self.access,
            "fetched_at": self.fetched_at,
        }


def diff_snapshot(
    old: dict[str, Any] | None,
    new: Snapshot,
) -> list[str]:
    """Return a list of human-readable changes between old and new state.

    Empty list means nothing changed worth notifying about. The very first
    time we see a URL (``old`` is empty), we don't generate a diff — the
    initial snapshot establishes the baseline silently.
    """
    if not old:
        return []

    diffs: list[str] = []

    old_status = old.get("status", "active")
    if old_status != new.status:
        if new.status == "sold":
            diffs.append("🟥 成約済みになりました")
        elif new.status == "removed":
            diffs.append("🟥 掲載終了（ページが見られなくなりました）")
        elif new.status == "active" and old_status in ("sold", "removed"):
            diffs.append("🟩 掲載が再開されました")

    op = old.get("price_jpy")
    np_ = new.price_jpy
    if op and np_ and op != np_:
        sign = "値下げ ⬇" if np_ < op else "値上げ ⬆"
        diffs.append(f"💴 価格変更: {op // 10_000:,}万円 → {np_ // 10_000:,}万円 ({sign})")

    old_layout = old.get("layout", "")
    if old_layout and new.layout and old_layout != new.layout:
        diffs.append(f"📐 間取り変更: {old_layout} → {new.layout}")

    return diffs


# ---------------------------------------------------------------------------
# Detail-page fetchers (per portal)
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat()


async def fetch_listing_snapshot(
    client: httpx.AsyncClient,
    url: str,
) -> Snapshot | None:
    """Dispatch to the right portal-specific fetcher."""
    if "suumo.jp" in url:
        return await _fetch_suumo_snapshot(client, url)
    if "athome.co.jp" in url:
        return await _fetch_athome_snapshot(client, url)
    if "homes.co.jp" in url:
        return await _fetch_homes_snapshot(client, url)
    logger.warning("unsupported portal: %s", url)
    return None


# --- SUUMO ---------------------------------------------------------------

_SUUMO_SOLD_TOKENS = ("成約済み", "ご成約", "販売を終了", "申込み済み")


async def _fetch_suumo_snapshot(
    client: httpx.AsyncClient,
    url: str,
) -> Snapshot | None:
    try:
        resp = await client.get(
            url,
            headers={**_SUUMO_HEADERS, "Referer": "https://suumo.jp/"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("suumo detail fetch failed (%s): %s", url, exc)
        return None
    if resp.status_code in (404, 410):
        return Snapshot(url=url, status="removed", fetched_at=_now_iso())
    if resp.status_code != 200:
        logger.info("suumo detail HTTP %d for %s", resp.status_code, url)
        return None

    html = resp.text
    fields = _suumo_parse_detail(html)
    if any(tok in html for tok in _SUUMO_SOLD_TOKENS):
        status = "sold"
    elif not fields.get("price_jpy"):
        # Likely a removed listing showing a placeholder page.
        status = "unknown"
    else:
        status = "active"

    return Snapshot(
        url=url,
        status=status,
        name=fields.get("name", ""),
        price_jpy=fields.get("price_jpy"),
        address=fields.get("address", ""),
        layout=fields.get("layout", ""),
        access=fields.get("access", ""),
        fetched_at=_now_iso(),
    )


def _suumo_parse_detail(html: str) -> dict[str, Any]:
    """Extract name/price/address/layout/access from a SUUMO detail page."""
    out: dict[str, Any] = {}

    # 物件名 — sometimes in <title>, but also in the first dl
    mt = re.search(r"<title>【SUUMO】([^<]+?)\s*中古", html)
    if mt:
        out["name"] = mt.group(1).strip()

    text = _flatten(html)

    pm = re.search(r"価格[^\d]{0,40}([\d,]+)\s*万円", text)
    if pm:
        try:
            out["price_jpy"] = int(pm.group(1).replace(",", "")) * 10_000
        except ValueError:
            pass

    # Address: after the "住所" label, skip helper words like "ヒント" / spaces,
    # then capture the prefecture-prefixed address up to a separator.
    am = re.search(r"住所(?:\s|ヒント)*\s*([^\s\[<]+(?:県|府|都)[^\s\[<]+)", text)
    if am:
        out["address"] = am.group(1).strip()

    # Layout: same — "間取り ヒント 5DK+S（納戸）" / "間取り 4LDK".
    # Normalise full-width digits/letters so diffs don't trigger on cosmetic
    # text changes between fetches.
    lm = re.search(
        r"間取り[^\d０-９]{0,30}"
        r"([\d０-９]+[ＬLＤDＫKＳSＲR][ＬLＤDＫKＳSＲR\+＋]*"
        r"(?:\+[ＳS](?:（[^）]+）)?)?)",
        text,
    )
    if lm:
        out["layout"] = (
            lm.group(1)
            .strip()
            .translate(
                str.maketrans(
                    "０１２３４５６７８９ＬＤＫＳＲ＋",
                    "0123456789LDKSR+",
                )
            )
        )

    # Access: capture the "交通" segment (same as listing alert enrichment).
    for m in re.finditer(r"交通", html):
        ctx = html[m.start() : m.start() + 4000]
        ctx2 = re.sub(r"<br\s*/?>", "\n", ctx, flags=re.IGNORECASE)
        t = re.sub(r"<script.*?</script>", " ", ctx2, flags=re.DOTALL)
        t = re.sub(r"<style.*?</style>", " ", t, flags=re.DOTALL)
        t = re.sub(r"<[^>]+>", " ", t)
        t = re.sub(r"&nbsp;", " ", t)
        t = re.sub(r"\[\s*乗り換え案内\s*\]", " ", t)
        t = re.sub(r"[ \t]+", " ", t)
        lines = [
            ln.strip()
            for ln in t.split("\n")
            if "歩" in ln  # both 徒歩 and abbreviated 歩
        ]
        joined = "\n".join(lines[:8])
        if joined:
            out["access"] = joined
            break

    return out


def _flatten(html: str) -> str:
    """HTML → single-line text suitable for label-based regex extraction."""
    t = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.DOTALL)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"&nbsp;", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t


# --- athome ---------------------------------------------------------------


async def _fetch_athome_snapshot(
    client: httpx.AsyncClient,
    url: str,
) -> Snapshot | None:
    try:
        resp = await client.get(
            url,
            headers={**_ATHOME_HEADERS, "Referer": "https://www.athome.co.jp/"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("athome detail fetch failed (%s): %s", url, exc)
        return None
    if resp.status_code in (404, 410):
        return Snapshot(url=url, status="removed", fetched_at=_now_iso())
    if resp.status_code != 200:
        return None

    html = resp.text
    # athome detail pages also embed the bukken JSON; reuse the list parser.
    bl = _extract_bukken_list(html)
    if bl:
        item = bl[0]
        kakaku = str(item.get("kakaku") or "")
        pm = re.search(r"([\d,]+)", kakaku)
        price = int(pm.group(1).replace(",", "")) * 10_000 if pm else None
        return Snapshot(
            url=url,
            status="active" if price else "unknown",
            name=(item.get("title") or "").strip(),
            price_jpy=price,
            address=(item.get("location") or "").strip(),
            layout=(item.get("madori") or "")
            .translate(
                str.maketrans("０１２３４５６７８９ＬＤＫＳＲ", "0123456789LDKSR"),
            )
            .strip(),
            access="",
            fetched_at=_now_iso(),
        )
    # Fallback: 成約 detection on the rendered page.
    if "公開を終了" in html or "掲載終了" in html:
        return Snapshot(url=url, status="sold", fetched_at=_now_iso())
    return Snapshot(url=url, status="unknown", fetched_at=_now_iso())


# --- HOME'S --------------------------------------------------------------


async def _fetch_homes_snapshot(
    client: httpx.AsyncClient,
    url: str,
) -> Snapshot | None:
    headers = {
        "User-Agent": _SUUMO_HEADERS["User-Agent"],
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ja,en;q=0.9",
        "Referer": "https://www.homes.co.jp/",
    }
    try:
        resp = await client.get(url, headers=headers)
    except Exception as exc:  # noqa: BLE001
        logger.info("homes detail fetch failed (%s): %s", url, exc)
        return None
    if resp.status_code in (404, 410):
        return Snapshot(url=url, status="removed", fetched_at=_now_iso())
    if resp.status_code != 200:
        return None

    html = resp.text
    # HOME'S "掲載終了" page is shown in place of an active listing.
    if "掲載が終了" in html or "ご紹介できる物件がありません" in html:
        return Snapshot(url=url, status="sold", fetched_at=_now_iso())

    text = _flatten(html)
    name_m = re.search(r"<title>([^<]+?)【LIFULL HOME", html) or re.search(
        r"<title>([^<]+?)\|",
        html,
    )
    name = name_m.group(1).strip() if name_m else ""
    pm = re.search(r"価格[^\d]{0,30}([\d,]+)\s*万円", text)
    price = int(pm.group(1).replace(",", "")) * 10_000 if pm else None
    am = re.search(r"所在地[^\w]{0,5}([兵庫|大阪|京都|奈良|滋賀][^\s]+)", text)
    address = am.group(1).strip() if am else ""
    lm = re.search(r"間取り[^\w]{0,5}([\dＬLＤDＫKＳSＲR\+]+)", text)
    layout = lm.group(1).strip() if lm else ""

    return Snapshot(
        url=url,
        status="active" if price else "unknown",
        name=name,
        price_jpy=price,
        address=address,
        layout=layout,
        access="",
        fetched_at=_now_iso(),
    )


# ---------------------------------------------------------------------------
# Pipeline + message formatting
# ---------------------------------------------------------------------------


def _format_change_block(snap: Snapshot, diffs: list[str]) -> str:
    lines = [f"📌 {snap.name or '(物件名不明)'}"]
    if snap.address:
        lines.append(f"📍 {snap.address}")
    if snap.layout:
        lines.append(f"📐 {snap.layout}")
    if snap.price_jpy:
        lines.append(f"💰 現在 {snap.price_jpy // 10_000:,}万円")
    lines.append("— 変更 —")
    lines.extend(diffs)
    lines.append(f"🔗 {snap.url}")
    return "\n".join(lines)


_LISTINGS_PER_MESSAGE = 4


def build_mylist_messages(
    changes: list[tuple[Snapshot, list[str]]],
) -> list[str]:
    if not changes:
        return []
    blocks = [_format_change_block(s, d) for s, d in changes]
    header = f"👀 マイリスト更新 {len(changes)}件"
    out: list[str] = []
    for i in range(0, len(blocks), _LISTINGS_PER_MESSAGE):
        chunk = blocks[i : i + _LISTINGS_PER_MESSAGE]
        prefix = header if i == 0 else "（続き）"
        out.append(prefix + "\n\n" + "\n\n".join(chunk))
    return out


async def run_mylist_check(
    *,
    store: MyListStore,
    channel_token: str,
    target_id: str = "",
    dry_run: bool = False,
    proxy: str = "",
) -> dict[str, Any]:
    """Fetch every URL in the my-list, diff against last snapshot, notify."""
    urls = store.load_urls()
    if not urls:
        return {
            "checked": 0,
            "changes": 0,
            "sent": 0,
            "errors": [],
            "dry_run": dry_run,
        }

    old_snaps = store.load_snapshots()
    new_snaps: dict[str, dict[str, Any]] = dict(old_snaps)
    changes: list[tuple[Snapshot, list[str]]] = []
    errors: list[str] = []

    sem = asyncio.Semaphore(4)

    async def _one(client: httpx.AsyncClient, url: str) -> None:
        async with sem:
            snap = await fetch_listing_snapshot(client, url)
            if snap is None:
                errors.append(f"取得失敗: {url}")
                return
            diffs = diff_snapshot(old_snaps.get(url), snap)
            new_snaps[url] = snap.to_dict()
            if diffs:
                changes.append((snap, diffs))

    try:
        async with httpx.AsyncClient(
            timeout=25,
            follow_redirects=True,
            http2=False,
            proxy=proxy or None,
        ) as client:
            await asyncio.gather(*[_one(client, u) for u in urls])
    except Exception as exc:  # noqa: BLE001
        errors.append(f"my-list fetch error: {exc!s}")

    sent = 0
    if changes and not dry_run:
        connector = LineNotifyConnector(
            channel_token=channel_token,
            target_id=target_id,
        )
        result = await connector.fetch(messages=build_mylist_messages(changes))
        sent = result.data.get("sent", 0)
        errors.extend(result.errors)

    # Persist snapshots whether or not we sent — first run establishes
    # baselines silently; subsequent runs diff against the new baseline.
    store.save_snapshots(new_snaps)

    return {
        "checked": len(urls),
        "changes": len(changes),
        "sent": sent,
        "errors": errors,
        "dry_run": dry_run,
        "diffs": [{"url": s.url, "status": s.status, "changes": d} for s, d in changes],
    }
