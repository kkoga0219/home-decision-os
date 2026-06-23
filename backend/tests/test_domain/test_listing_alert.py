"""Tests for the 塚口 alert orchestration (message formatting + pipeline)."""

import asyncio

from app.services.listing_alert import build_messages, run_tsukaguchi_alert


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
