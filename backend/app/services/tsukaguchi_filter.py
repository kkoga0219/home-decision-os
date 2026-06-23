"""Walk-distance qualification rule for the 塚口 (Tsukaguchi) area.

There are two distinct stations named 塚口:
  - 阪急塚口 (Hankyu): 阪急神戸線 / 阪急伊丹線
  - JR塚口  (JR):     JR宝塚線 (福知山線)

And one neighbouring JR station that the user treats as equivalent for
the "JR side" of rule (B):
  - 猪名寺    (JR):     JR宝塚線 (福知山線) — one stop north of JR塚口

The user's rule for a property to be "interesting":

    (A) 阪急塚口 within 10 min walk
        OR
    (B) 阪急塚口 within 15 min walk
        AND (JR塚口 within 15 min walk OR 猪名寺 within 15 min walk)

This module turns a free-text access string (as scraped from SUUMO /
HOME'S / athome listing cards or detail pages) into per-station walk
times and evaluates that rule. It is pure / network-free so it can be
unit-tested directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Thresholds from the requirement.
HANKYU_PRIMARY_MAX = 10  # rule (A): 阪急塚口 alone
BOTH_MAX = 15  # rule (B): 阪急 AND (JR塚口 or 猪名寺), all within this

_STATION = "塚口"

# Separators between multiple access lines in a single string.
_SPLIT_RE = re.compile(r"[／/、,，\n\t]|(?<=分)\s+(?=\S*?線)")
# SUUMO list cards write "徒歩11分"; detail pages abbreviate to "歩11分".
# Match either, but only after the segment has already passed
# _segment_is_walk_only() so "停歩2分" (a bus-stop walk) never reaches us.
_WALK_RE = re.compile(r"徒?歩\s*(\d+)\s*分")


@dataclass(frozen=True)
class TsukaguchiAccess:
    """Parsed walk times (minutes) to each relevant station."""

    hankyu: int | None = None  # 阪急塚口
    jr: int | None = None  # JR塚口
    inadera: int | None = None  # 猪名寺 (JR福知山線, JR塚口 alternative)
    unknown: int | None = None  # 塚口 with no identifiable operator


@dataclass(frozen=True)
class QualificationResult:
    qualifies: bool
    reason: str
    access: TsukaguchiAccess


_LAYOUT_ROOMS_RE = re.compile(r"(\d+)")


def layout_room_count(layout: str) -> int | None:
    """Number of rooms from a layout string (e.g. '3LDK' → 3).

    Recognises single-room layouts written without a leading digit
    (ワンルーム / studio → 1). Returns None only when truly unparseable.
    """
    if not layout:
        return None
    s = layout.strip()
    if "ワンルーム" in s or "ステュディオ" in s or "ストゥディオ" in s:
        return 1
    m = _LAYOUT_ROOMS_RE.match(s)
    return int(m.group(1)) if m else None


def layout_meets_minimum(layout: str, min_rooms: int = 3) -> bool:
    """True if the layout has at least ``min_rooms`` rooms.

    Unknown / unparseable layouts pass (better to over-notify than to drop a
    good property whose layout simply did not parse). Used to honour the
    "3LDK以上" requirement.
    """
    rooms = layout_room_count(layout)
    if rooms is None:
        return True
    return rooms >= min_rooms


def _classify_operator(segment: str) -> str:
    """Classify a 塚口 access segment as 'hankyu', 'jr' or 'unknown'."""
    if "阪急" in segment or "ハンキュウ" in segment:
        return "hankyu"
    # SUUMO renders "JR" full-width as "ＪＲ"; match both.
    if (
        re.search(r"JR", segment, re.IGNORECASE)
        or "ＪＲ" in segment
        or "福知山線" in segment
        or "宝塚線" in segment
    ):
        return "jr"
    return "unknown"


def _min(current: int | None, candidate: int) -> int:
    return candidate if current is None else min(current, candidate)


def _segment_is_walk_only(segment: str) -> bool:
    """True if a segment is a pure-walking access (no bus, no shuttle).

    Rejects entries like "阪急神戸線 「塚口」駅 【バス】21分 城ノ堀 停歩2分"
    where the property is NOT within walking distance of 塚口 — it's a bus
    ride away. Such entries previously slipped through because the regex
    only checked "徒歩N分".
    """
    if "バス" in segment or "ｂｕｓ" in segment.lower():
        return False
    if "シャトル" in segment:
        return False
    return True


def parse_tsukaguchi_access(access: str) -> TsukaguchiAccess:
    """Extract the shortest walk time to each relevant station.

    Stations considered: 塚口 (阪急 or JR), 猪名寺 (JR alternative for
    rule B). Only segments that are a pure walking access (no bus /
    shuttle) and that contain a "徒歩N分" component are kept.
    """
    if not access:
        return TsukaguchiAccess()

    hankyu: int | None = None
    jr: int | None = None
    inadera: int | None = None
    unknown: int | None = None

    for raw in _SPLIT_RE.split(access):
        segment = (raw or "").strip()
        if not segment:
            continue
        if not _segment_is_walk_only(segment):
            continue
        m = _WALK_RE.search(segment)
        if not m:
            continue
        minutes = int(m.group(1))

        if "猪名寺" in segment:
            inadera = _min(inadera, minutes)
            continue
        if _STATION not in segment:
            continue
        op = _classify_operator(segment)
        if op == "hankyu":
            hankyu = _min(hankyu, minutes)
        elif op == "jr":
            jr = _min(jr, minutes)
        else:
            unknown = _min(unknown, minutes)

    return TsukaguchiAccess(
        hankyu=hankyu,
        jr=jr,
        inadera=inadera,
        unknown=unknown,
    )


def evaluate_access(
    access: str,
    *,
    assume_unknown_is_hankyu: bool = False,
) -> QualificationResult:
    """Evaluate the qualification rule against an access string.

    Parameters
    ----------
    assume_unknown_is_hankyu :
        OFF by default. All three portals (SUUMO / HOME'S / athome) print
        the rail operator next to the station name, so "operator unknown"
        in practice means the segment was garbled — assuming 阪急 there
        only added false positives. Set True to re-enable the heuristic.
    """
    parsed = parse_tsukaguchi_access(access)

    hankyu = parsed.hankyu
    jr = parsed.jr
    inadera = parsed.inadera

    # Rule (A): 阪急塚口 within 10 minutes.
    if hankyu is not None and hankyu <= HANKYU_PRIMARY_MAX:
        return QualificationResult(
            True,
            f"阪急塚口 徒歩{hankyu}分 (≤{HANKYU_PRIMARY_MAX}分)",
            parsed,
        )

    # Rule (B): 阪急塚口 ≤15 AND (JR塚口 ≤15 OR 猪名寺 ≤15).
    if hankyu is not None and hankyu <= BOTH_MAX:
        jr_ok = jr is not None and jr <= BOTH_MAX
        ina_ok = inadera is not None and inadera <= BOTH_MAX
        if jr_ok or ina_ok:
            # Choose the closer of JR塚口/猪名寺 for the message.
            if jr_ok and (not ina_ok or jr <= inadera):
                jr_part = f"JR塚口 徒歩{jr}分"
            else:
                jr_part = f"猪名寺 徒歩{inadera}分"
            return QualificationResult(
                True,
                f"阪急塚口 徒歩{hankyu}分・{jr_part} (≤{BOTH_MAX}分)",
                parsed,
            )

    # Ambiguous: operator not printed but 塚口 is close.
    if (
        assume_unknown_is_hankyu
        and parsed.unknown is not None
        and parsed.unknown <= HANKYU_PRIMARY_MAX
    ):
        return QualificationResult(
            True,
            f"塚口 徒歩{parsed.unknown}分 (路線不明・阪急と推定)",
            parsed,
        )

    return QualificationResult(False, "条件外", parsed)
