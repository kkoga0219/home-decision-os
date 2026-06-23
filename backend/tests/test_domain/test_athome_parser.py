"""Tests for athome TransferState JSON parsing + layout filtering."""

import json

from app.connectors.athome_search import _extract_bukken_list, _parse_athome_page
from app.services.tsukaguchi_filter import (
    layout_meets_minimum,
    layout_room_count,
)


def _make_html(bukken_list):
    inner = {"data": {"bukkenData": {"bukkenList": bukken_list}}}
    body = json.dumps(inner, ensure_ascii=False)
    state = {"G.text.http://bff/csite-bff/bukken/list": {"body": body}}
    blob = json.dumps(state, ensure_ascii=False)
    return f'<html><body><script type="application/json">{blob}</script></body></html>'


SAMPLE_BUKKEN = [
    {
        "bukkenNo": "1234567890",
        "title": "グリーンハイツ塚口 4階 ３ＬＤＫ",
        "kakaku": "730",
        "madori": "３ＬＤＫ",
        "location": "尼崎市塚口本町",
        "kaiinAccess": "阪急神戸線/塚口 徒歩3分",
        "bukkenAccess": [
            {"name": "阪急神戸線 「塚口」駅 徒歩3分"},
            {"name": "ＪＲ福知山線 「塚口」駅 徒歩12分"},
        ],
        "areaInfo": {"area": "65.4m²", "tsubo": "19.7坪"},
    }
]


class TestExtractBukkenList:
    def test_extracts_list(self):
        html = _make_html(SAMPLE_BUKKEN)
        bl = _extract_bukken_list(html)
        assert len(bl) == 1
        assert bl[0]["bukkenNo"] == "1234567890"

    def test_no_json_returns_empty(self):
        assert _extract_bukken_list("<html>nothing</html>") == []


class TestParseAthomePage:
    def test_maps_fields(self):
        html = _make_html(SAMPLE_BUKKEN)
        listings = _parse_athome_page(html, "mansion")
        assert len(listings) == 1
        ls = listings[0]
        assert ls["source"] == "athome"
        assert ls["name"].startswith("グリーンハイツ塚口")
        assert ls["price_jpy"] == 7_300_000
        assert ls["layout"] == "3LDK"
        assert ls["url"] == "https://www.athome.co.jp/mansion/1234567890/"
        assert ls["floor_area_sqm"] == 65.4

    def test_house_url_uses_kodate(self):
        html = _make_html(SAMPLE_BUKKEN)
        ls = _parse_athome_page(html, "house")[0]
        assert "/kodate/" in ls["url"]

    def test_access_slash_replaced_keeps_line_attached(self):
        """kaiinAccess '阪急神戸線/塚口' must not lose its 阪急 line on split."""
        from app.services.tsukaguchi_filter import evaluate_access

        html = _make_html(SAMPLE_BUKKEN)
        ls = _parse_athome_page(html, "mansion")[0]
        verdict = evaluate_access(ls["access"])
        assert verdict.qualifies
        # 阪急 detected (not "路線不明")
        assert "阪急塚口" in verdict.reason


class TestLayoutRoomCount:
    def test_basic(self):
        assert layout_room_count("3LDK") == 3
        assert layout_room_count("4SLDK") == 4

    def test_one_room_words(self):
        assert layout_room_count("ワンルーム") == 1

    def test_empty(self):
        assert layout_room_count("") is None


class TestLayoutMeetsMinimum:
    def test_3ldk_passes(self):
        assert layout_meets_minimum("3LDK", 3)

    def test_2ldk_fails(self):
        assert not layout_meets_minimum("2LDK", 3)

    def test_one_room_fails(self):
        assert not layout_meets_minimum("ワンルーム", 3)

    def test_unknown_passes(self):
        assert layout_meets_minimum("", 3)
