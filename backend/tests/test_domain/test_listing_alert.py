"""Tests for the 塚口 alert orchestration (message formatting + pipeline)."""

import asyncio

from app.services.listing_alert import (
    _group_listings,
    _passes_age_filter,
    build_messages,
    run_tsukaguchi_alert,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


SAMPLE = [
    {
        "property_type_label": "中古マンション",
        "name": "プラウド塚口",
        "price_text": "3,480万円",
        "match_reason": "阪急塚口 徒歩6分 (≤10分)",
        "address": "兵庫県尼崎市塚口本町",
        "url": "https://suumo.jp/ms/chuko/x/nc_1/",
    },
    {
        "property_type_label": "中古戸建て",
        "name": "塚口の家",
        "price_jpy": 42_800_000,
        "match_reason": "阪急塚口 徒歩9分・JR塚口 徒歩13分 (両駅 ≤15分)",
        "url": "https://www.homes.co.jp/kodate/b-2/",
    },
]


class TestBuildMessages:
    def test_empty(self):
        assert build_messages([]) == []

    def test_header_and_content(self):
        msgs = build_messages(SAMPLE)
        assert len(msgs) == 1
        assert "新着物件 2件" in msgs[0]
        assert "プラウド塚口" in msgs[0]
        assert "中古戸建て" in msgs[0]
        # price_jpy fallback rendered as 万円
        assert "4,280万円" in msgs[0]

    def test_chunking(self):
        many = SAMPLE * 4  # 8 listings → 2 messages (5 per message)
        msgs = build_messages(many)
        assert len(msgs) == 2
        assert "（続き）" in msgs[1]

    def test_truncated_note(self):
        msgs = build_messages(SAMPLE, truncated=7)
        assert any("ほか 7 件" in m for m in msgs)


def _ls(name, price, layout="3LDK", url="u", walk=5, **kw):
    d = {
        "name": name,
        "price_jpy": price,
        "layout": layout,
        "url": url,
        "match_reason": f"阪急塚口 徒歩{walk}分 (≤10分)",
        "property_type": "mansion",
        "property_type_label": "中古マンション",
    }
    d.update(kw)
    return d


class TestGroupListings:
    def test_same_building_same_room_collapses(self):
        items = [
            _ls("パレ・ロワイヤル塚口", 49_800_000, url="u1", walk=3),
            _ls("パレ・ロワイヤル塚口", 49_800_000, url="u2", walk=4),
            _ls("パレ・ロワイヤル塚口", 49_800_000, url="u3", walk=6),
        ]
        groups = _group_listings(items)
        assert len(groups) == 1
        rep = groups[0]
        assert rep["group_size"] == 3
        # representative = shortest walk
        assert rep["url"] == "u1"
        assert set(rep["group_urls"]) == {"u1", "u2", "u3"}

    def test_different_price_stays_separate(self):
        items = [
            _ls("Aマンション", 30_000_000, url="u1"),
            _ls("Aマンション", 35_000_000, url="u2"),
        ]
        assert len(_group_listings(items)) == 2

    def test_different_layout_stays_separate(self):
        items = [
            _ls("Aマンション", 30_000_000, layout="3LDK", url="u1"),
            _ls("Aマンション", 30_000_000, layout="4LDK", url="u2"),
        ]
        assert len(_group_listings(items)) == 2

    def test_fullwidth_building_number_normalised(self):
        items = [
            _ls("塚口さんさんタウン２番館", 49_900_000, url="u1"),
            _ls("塚口さんさんタウン2番館", 49_900_000, url="u2"),
        ]
        assert len(_group_listings(items)) == 1

    def test_message_shows_duplicate_count(self):
        items = [
            _ls("パレ・ロワイヤル塚口", 49_800_000, url="https://x/1", walk=3),
            _ls("パレ・ロワイヤル塚口", 49_800_000, url="https://x/2", walk=4),
        ]
        groups = _group_listings(items)
        msg = build_messages(groups)[0]
        assert "別掲載 1件" in msg
        assert "https://x/2" in msg


class TestAgeFilter:
    def test_mansion_before_cutoff_excluded(self):
        assert not _passes_age_filter("mansion", {"built_year": 1989}, 1991)
        assert not _passes_age_filter("mansion", {"built_year": 1990}, 1991)

    def test_mansion_at_or_after_cutoff_kept(self):
        assert _passes_age_filter("mansion", {"built_year": 1991}, 1991)
        assert _passes_age_filter("mansion", {"built_year": 2005}, 1991)

    def test_house_exempt(self):
        assert _passes_age_filter("house", {"built_year": 1970}, 1991)

    def test_unknown_year_kept(self):
        assert _passes_age_filter("mansion", {}, 1991)

    def test_disabled_with_zero(self):
        assert _passes_age_filter("mansion", {"built_year": 1980}, 0)


class TestRunPipelineDryRun:
    def test_dry_run_no_token_no_send(self, tmp_path, monkeypatch):
        """dry_run still records state but never calls LINE."""
        path = tmp_path / "state.json"

        async def fake_gather(**kwargs):
            return list(SAMPLE)

        monkeypatch.setattr("app.services.listing_alert.gather_candidates", fake_gather)

        summary = _run(
            run_tsukaguchi_alert(
                channel_token="",
                target_id="",
                state_path=str(path),
                dry_run=True,
            )
        )
        assert summary["candidates"] == 2
        assert summary["new"] == 2
        assert summary["sent"] == 0
        assert summary["dry_run"] is True
        assert path.exists()

        # Second run: everything already seen → nothing new.
        summary2 = _run(
            run_tsukaguchi_alert(
                channel_token="",
                target_id="",
                state_path=str(path),
                dry_run=True,
            )
        )
        assert summary2["new"] == 0
