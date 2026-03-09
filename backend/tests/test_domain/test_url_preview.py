"""Tests for URL preview connector (parsing logic only, no HTTP)."""

from app.connectors.url_preview import _extract_meta, _parse_suumo_hints


class TestExtractMeta:
    def test_title(self):
        html = "<html><head><title>テストマンション | SUUMO</title></head></html>"
        meta = _extract_meta(html, "https://example.com")
        assert meta["title"] == "テストマンション | SUUMO"

    def test_ogp(self):
        html = '''<html><head>
            <meta property="og:title" content="OGPタイトル">
            <meta property="og:description" content="説明文">
        </head></html>'''
        meta = _extract_meta(html, "https://example.com")
        assert meta["title"] == "OGPタイトル"
        assert meta["description"] == "説明文"


class TestParseSuumoHints:
    def test_price(self):
        hints = _parse_suumo_hints("プラウド塚口 3,500万円", "")
        assert hints["hint_price_jpy"] == 35_000_000

    def test_area(self):
        hints = _parse_suumo_hints("65.5㎡", "")
        assert hints["hint_floor_area_sqm"] == 65.5

    def test_layout(self):
        hints = _parse_suumo_hints("3LDK", "")
        assert hints["hint_layout"] == "3LDK"

    def test_walking(self):
        hints = _parse_suumo_hints("", "塚口駅 徒歩5分")
        assert hints["hint_walking_minutes"] == 5

    def test_station(self):
        hints = _parse_suumo_hints("", "「塚口駅」徒歩3分")
        assert hints["hint_station_name"] == "塚口"

    def test_combined(self):
        title = "プラウド塚口 3LDK 65.5㎡ 3,500万円"
        desc = "JR福知山線「塚口駅」徒歩5分"
        hints = _parse_suumo_hints(title, desc)
        assert hints["hint_price_jpy"] == 35_000_000
        assert hints["hint_floor_area_sqm"] == 65.5
        assert hints["hint_layout"] == "3LDK"
        assert hints["hint_walking_minutes"] == 5
