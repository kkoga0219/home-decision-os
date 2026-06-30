"""Persistent "already seen" store for new-listing alerts.

A new-listing alert must remember which properties it has already notified
about, otherwise every run would re-send the entire result set. This keeps
that memory in a small JSON file whose path is configurable
(``HDOS_ALERT_STATE_PATH``), so it can be persisted across scheduled runs
(e.g. via actions/cache in a GitHub Actions workflow).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def listing_key(listing: dict[str, Any]) -> str:
    """Stable identity for a listing.

    Prefers the detail-page URL (unique per property). Falls back to a hash
    of source + name + price so listings without a parsed URL still dedupe.
    """
    url = (listing.get("url") or "").strip()
    if url:
        return url
    basis = "|".join(str(listing.get(k, "")) for k in ("source", "name", "price_jpy", "address"))
    return "hash:" + hashlib.sha1(basis.encode("utf-8")).hexdigest()


class AlertState:
    """Tracks listing keys that have already been notified."""

    def __init__(self, seen: dict[str, str] | None = None) -> None:
        # key -> ISO timestamp first seen
        self._seen: dict[str, str] = dict(seen or {})

    def __contains__(self, key: str) -> bool:
        return key in self._seen

    def __len__(self) -> int:
        return len(self._seen)

    def is_new(self, listing: dict[str, Any]) -> bool:
        return listing_key(listing) not in self._seen

    def mark(self, listing: dict[str, Any]) -> None:
        self.add_key(listing_key(listing))

    # Low-level key access — used for group-level dedup (same building +
    # room listed by several brokers under different URLs).
    def is_seen_key(self, key: str) -> bool:
        return key in self._seen

    def add_key(self, key: str) -> None:
        if key not in self._seen:
            self._seen[key] = _dt.datetime.now(_dt.UTC).isoformat()

    # --- persistence -------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> AlertState:
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            seen = raw.get("seen", {}) if isinstance(raw, dict) else {}
            return cls(seen=seen)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read alert state %s: %s", p, exc)
            return cls()

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": _dt.datetime.now(_dt.UTC).isoformat(),
            "count": len(self._seen),
            "seen": self._seen,
        }
        p.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
