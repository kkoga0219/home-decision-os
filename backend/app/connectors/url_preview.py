"""URL preview connector.

Fetches and parses property listing pages from Japanese real estate portals.
Supports SUUMO, LIFULL HOME'S, and generic OGP metadata extraction.

For SUUMO individual property pages, performs deep HTML parsing
to extract structured data (price, area, layout, station, built year, etc.).
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.connectors.base import BaseConnector, ConnectorResult

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


class URLPreviewConnector(BaseConnector):
    """Extracts property data from listing URLs."""

    @property
    def name(self) -> str:
        return "URL Preview"

    async def fetch(self, url: str, **kwargs: Any) -> ConnectorResult:
        if not url:
            return ConnectorResult(success=False, source=self.name, errors=["URL is empty"])

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers=HEADERS)
                resp.raise_for_status()
                html = resp.text
        except Exception as e:
            logger.error("URL fetch error: %s", e)
            return ConnectorResult(success=False, source=self.name, errors=[str(e)])

        meta = _extract_all(html, url)
        return ConnectorResult(success=True, source=self.name, data=meta)


# ---------------------------------------------------------------------------
# Extraction router
# ---------------------------------------------------------------------------

def _extract_all(html: str, url: str) -> dict[str, Any]:
    """Route to the appropriate parser based on URL domain."""
    data: dict[str, Any] = {"url": url}

    # Always extract basic meta/OGP
    data.update(_extract_meta(html))

    # Deep parse based on domain
    if "suumo.jp" in url:
        hints = _parse_suumo_deep(html, data.get("title", ""), data.get("description", ""))
        data.update(hints)
    elif "homes.co.jp" in url:
        hints = _parse_lifull_hints(html, data.get("title", ""), data.get("description", ""))
        data.update(hints)
    else:
        # Generic: try to extract from meta tags only
        hints = _parse_generic_hints(data.get("title", ""), data.get("description", ""))
        data.update(hints)

    return data


# ---------------------------------------------------------------------------
# Basic meta / OGP extraction
# ---------------------------------------------------------------------------

def _extract_meta(html: str) -> dict[str, Any]:
    """Extract OGP and basic meta tags from HTML."""
    data: dict[str, Any] = {}

    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if m:
        data["title"] = _clean(m.group(1))

    for prop in ("og:title", "og:description", "og:image", "og:site_name"):
        # Try both attribute orderings
        m = re.search(
            rf'<meta\s+(?:property|name)="{prop}"\s+content="([^"]*)"',
            html, re.IGNORECASE,
        )
        if not m:
            m = re.search(
                rf'<meta\s+content="([^"]*)"\s+(?:property|name)="{prop}"',
                html, re.IGNORECASE,
            )
        if m:
            key = prop.replace("og:", "")
            data[key] = _clean(m.group(1))

    m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html, re.IGNORECASE)
    if m and "description" not in data:
        data["description"] = _clean(m.group(1))

    return data


# ---------------------------------------------------------------------------
# SUUMO deep parser
# ---------------------------------------------------------------------------

def _parse_suumo_deep(html: str, title: str, description: str) -> dict[str, Any]:
    """Deep parse SUUMO property pages.

    Extracts from:
    1. OGP title/description (pipe-separated fields)
    2. HTML body: detail tables, spec sections, access info
    """
    hints: dict[str, Any] = {}

    # Strip HTML tags for body text search
    body_text = _strip_tags(html)
    combined_meta = f"{title} {description}"

    # --- Price ---
    # Try body first: look near "販売価格" or "価格" label
    price = _extract_near_label(body_text, [r"販売価格", r"価格"], r"([\d,]+)\s*万円")
    if not price:
        m = re.search(r"([\d,]+)\s*万円", combined_meta)
        if m:
            price = m.group(1)
    if price:
        hints["hint_price_jpy"] = int(price.replace(",", "")) * 10_000

    # --- Floor area ---
    area = _extract_near_label(body_text, [r"専有面積", r"面積"], r"([\d.]+)\s*[㎡m²]")
    if not area:
        m = re.search(r"([\d.]+)\s*[㎡m²]", combined_meta)
        if m:
            area = m.group(1)
    if area:
        hints["hint_floor_area_sqm"] = float(area)

    # --- Layout ---
    layout = _extract_near_label(body_text, [r"間取り"], r"(\d[LDKSR]{1,4})")
    if not layout:
        m = re.search(r"(\d[LDKSR]{1,4})", combined_meta, re.IGNORECASE)
        if m:
            layout = m.group(1)
    if layout:
        hints["hint_layout"] = layout.upper()

    # --- Walking minutes ---
    m = re.search(r"徒歩\s*(\d+)\s*分", body_text) or re.search(
        r"徒歩\s*(\d+)\s*分", combined_meta
    )
    if m:
        hints["hint_walking_minutes"] = int(m.group(1))

    # --- Station name ---
    # Pattern: 「駅名」駅 or XX線「駅名」
    m = (
        re.search(r"「([^」]{2,10})」駅", body_text)
        or re.search(r"「([^」]{2,10})」駅", combined_meta)
        or re.search(r"([^\s「」]{2,8})駅", combined_meta)
    )
    if m:
        hints["hint_station_name"] = m.group(1)

    # --- Built year ---
    # Patterns: "2018年3月築" "築2018年" "築年月2018年3月" "2018年築"
    m = (
        re.search(r"(\d{4})年\d{0,2}月?築", body_text)
        or re.search(r"築\s*(\d{4})年", body_text)
        or re.search(r"築年月\s*(\d{4})年", body_text)
        or re.search(r"(\d{4})年\d{0,2}月?築", combined_meta)
        or re.search(r"築\s*(\d{4})年", combined_meta)
    )
    if m:
        hints["hint_built_year"] = int(m.group(1))

    # --- Address ---
    # SUUMO: "所在地" label followed by address
    m = re.search(r"所在地\s*(.{5,40}?[市区町村].*?[丁目番号\d]+)", body_text)
    if m:
        hints["hint_address_text"] = m.group(1).strip()
    elif description:
        # Try to extract prefecture+city from description
        m = re.search(
            r"((?:東京都|北海道|(?:大阪|京都)府|.{2,3}県).{2,15}?[市区町村])",
            combined_meta,
        )
        if m:
            hints["hint_address_text"] = m.group(1)

    # --- Management fee ---
    m = re.search(r"管理費[^\d]{0,10}([\d,]+)\s*円", body_text)
    if m:
        hints["hint_management_fee_jpy"] = int(m.group(1).replace(",", ""))

    # --- Repair reserve ---
    m = re.search(r"修繕積立金[^\d]{0,10}([\d,]+)\s*円", body_text)
    if m:
        hints["hint_repair_reserve_jpy"] = int(m.group(1).replace(",", ""))

    # --- Total units ---
    m = re.search(r"(?:総戸数|全)\s*(\d+)\s*戸", body_text)
    if m:
        hints["hint_total_units"] = int(m.group(1))

    # --- Floor number ---
    # "所在階 5階" or "5階/10階建"
    m = re.search(r"(?:所在階|所在)[^\d]{0,5}(\d+)\s*階", body_text)
    if m:
        hints["hint_floor_number"] = int(m.group(1))

    # --- Total floors ---
    m = re.search(r"(\d+)\s*階建", body_text)
    if m:
        hints["hint_total_floors"] = int(m.group(1))

    return hints


# ---------------------------------------------------------------------------
# LIFULL HOME'S parser (basic)
# ---------------------------------------------------------------------------

def _parse_lifull_hints(html: str, title: str, description: str) -> dict[str, Any]:
    """Parse LIFULL HOME'S property pages."""
    body_text = _strip_tags(html)
    return _parse_generic_hints(title, description, body_text)


# ---------------------------------------------------------------------------
# Generic parser (any site)
# ---------------------------------------------------------------------------

def _parse_generic_hints(title: str, description: str, body_text: str = "") -> dict[str, Any]:
    """Try to extract property data from any page using common Japanese RE patterns."""
    hints: dict[str, Any] = {}
    combined = f"{title} {description} {body_text}"

    m = re.search(r"([\d,]+)\s*万円", combined)
    if m:
        hints["hint_price_jpy"] = int(m.group(1).replace(",", "")) * 10_000

    m = re.search(r"([\d.]+)\s*[㎡m²]", combined)
    if m:
        hints["hint_floor_area_sqm"] = float(m.group(1))

    m = re.search(r"(\d[LDKSR]{1,4})", combined, re.IGNORECASE)
    if m:
        hints["hint_layout"] = m.group(1).upper()

    m = re.search(r"徒歩\s*(\d+)\s*分", combined)
    if m:
        hints["hint_walking_minutes"] = int(m.group(1))

    m = re.search(r"「([^」]{2,10})」駅", combined) or re.search(r"([^\s「」]{2,8})駅", combined)
    if m:
        hints["hint_station_name"] = m.group(1)

    m = re.search(r"(\d{4})年\d{0,2}月?築", combined) or re.search(r"築\s*(\d{4})年", combined)
    if m:
        hints["hint_built_year"] = int(m.group(1))

    m = re.search(r"管理費[^\d]{0,10}([\d,]+)\s*円", combined)
    if m:
        hints["hint_management_fee_jpy"] = int(m.group(1).replace(",", ""))

    m = re.search(r"修繕積立金[^\d]{0,10}([\d,]+)\s*円", combined)
    if m:
        hints["hint_repair_reserve_jpy"] = int(m.group(1).replace(",", ""))

    return hints


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_near_label(
    text: str,
    label_patterns: list[str],
    value_pattern: str,
    window: int = 50,
) -> str | None:
    """Extract a value that appears near a label in the text.

    Searches for each label pattern, then looks for the value pattern
    within `window` characters after the label.
    """
    for label_pat in label_patterns:
        m = re.search(label_pat, text)
        if m:
            start = m.end()
            snippet = text[start : start + window]
            vm = re.search(value_pattern, snippet)
            if vm:
                return vm.group(1)
    return None


def _strip_tags(html: str) -> str:
    """Remove HTML tags, collapse whitespace."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#\d+;", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _clean(s: str) -> str:
    """Clean HTML entities and whitespace from a string."""
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&lt;", "<", s)
    s = re.sub(r"&gt;", ">", s)
    s = re.sub(r"&quot;", '"', s)
    s = re.sub(r"&#\d+;", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
