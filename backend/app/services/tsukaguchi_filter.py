"""Walk-distance qualification rule for the 塚口 (Tsukaguchi) area.

There are two distinct stations named 塚口:
  - 阪急塚口 (Hankyu): 阪急神戸線 / 阪急伊丹線
  - JR塚口  (JR):     JR宝塚線 (福知山線)

The user's rule for a property to be "interesting":

    (A) 阪急塚口 within 10 min walk
        OR
    (B) BOTH JR塚口 within 15 min walk AND 阪急塚口 within 15 min walk

This module turns a free-text access string (as scraped from SUUMO /
HOME'S / athome listing cards or detail pages) into per-operator walk
times to 塚口 and evaluates that rule. It is pure / network-free so it
can be unit-tested directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Thresholds from the requirement.
HANKYU_PRIMARY_MAX = 10  # rule (A): 阪急塚口 alone
BOTH_MAX = 15  # rule (B): both stations

_STATION = "塚口"

# Separators between multiple access lines in a single string.
_SPLIT_RE = re.compile(r"[／/、,，\n\t]|(?<=分)\s+(?=\S*?線)")
_WALK_RE = re.compile(r"徒歩\s*(\d+)\s*分")


@dataclass(frozen=True)
class TsukaguchiAccess:
    """Parsed walk times (minutes) to 塚口, per rail operator."""

    hankyu: int | None = None  # 阪急塚口
    jr: int | None = None  # JR塚口
    unknown: int | None = None  # 塚口 with no identifiable operator


@dataclass(frozen=True)
class QualificationResult:
    qualifies: bool
    reason: str
    access: TsukaguchiAccess


def _classify_operator(segment: str) -> str:
    """Classify a 塚口 access segment as 'hankyu', 'jr' or 'unknown'."""
    if "阪急" in segment or "ハンキュウ" in segment:
        return "hankyu"
    if re.search(r"JR", segment, re.IGNORECASE) or "福知山線" in segment or "宝塚線" in segment:
        return "jr"
    return "unknown"


def _min(current: int | None, candidate: int) -> int:
    return candidate if current is None else min(current, candidate)


def parse_tsukaguchi_access(access: str) -> TsukaguchiAccess:
    """Extract the shortest walk time to 塚口 for each operator.

    Only segments that mention the 塚口 station are considered; walk times
    to other stations are ignored.
    """
    if not access:
        return TsukaguchiAccess()

    hankyu: int | None = None
    jr: int | None = None
    unknown: int | None = None

    for raw in _SPLIT_RE.split(access):
        segment = (raw or "").strip()
        if not segment or _STATION not in segment:
            continue
        m = _WALK_RE.search(segment)
        if not m:
            continue
        minutes = int(m.group(1))
        op = _classify_operator(segment)
        if op == "hankyu":
            hankyu = _min(hankyu, minutes)
        elif op == "jr":
            jr = _min(jr, minutes)
        else:
            unknown = _min(unknown, minutes)

    return TsukaguchiAccess(hankyu=hankyu, jr=jr, unknown=unknown)


def evaluate_access(
    access: str,
    *,
    assume_unknown_is_hankyu: bool = True,
) -> QualificationResult:
    """Evaluate the qualification rule against an access string.

    Parameters
    ----------
    assume_unknown_is_hankyu :
        Listing cards often print just "塚口駅 徒歩9分" without naming the
        operator. In the 塚口 area such listings almost always refer to 阪急
        塚口, and for an alert it is better to over-notify than to miss a
        match. When True (default), an unidentified 塚口 within the 10-min
        threshold satisfies rule (A) (flagged as 推定 in the reason).
    """
    parsed = parse_tsukaguchi_access(access)

    hankyu = parsed.hankyu
    jr = parsed.jr

    # Rule (A): 阪急塚口 within 10 minutes.
    if hankyu is not None and hankyu <= HANKYU_PRIMARY_MAX:
        return QualificationResult(
            True,
            f"阪急塚口 徒歩{hankyu}分 (≤{HANKYU_PRIMARY_MAX}分)",
            parsed,
        )

    # Rule (B): both JR塚口 and 阪急塚口 within 15 minutes.
    if hankyu is not None and jr is not None and hankyu <= BOTH_MAX and jr <= BOTH_MAX:
        return QualificationResult(
            True,
            f"阪急塚口 徒歩{hankyu}分・JR塚口 徒歩{jr}分 (両駅 ≤{BOTH_MAX}分)",
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
