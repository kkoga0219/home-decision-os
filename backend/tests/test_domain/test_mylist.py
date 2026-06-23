"""Tests for the my-list watcher (store + diff + message formatting)."""

from app.services.mylist import (
    MyListStore,
    Snapshot,
    build_mylist_messages,
    diff_snapshot,
)


class TestMyListStore:
    def test_load_urls_skips_blanks_and_comments(self, tmp_path):
        p = tmp_path / "mylist.txt"
        p.write_text(
            "# header comment\n"
            "\n"
            "https://suumo.jp/ms/chuko/a/nc_1/\n"
            "  # indented comment\n"
            " https://suumo.jp/ms/chuko/b/nc_2/ \n",
            encoding="utf-8",
        )
        store = MyListStore(p, tmp_path / "snaps.json")
        assert store.load_urls() == [
            "https://suumo.jp/ms/chuko/a/nc_1/",
            "https://suumo.jp/ms/chuko/b/nc_2/",
        ]

    def test_load_urls_dedupes(self, tmp_path):
        p = tmp_path / "mylist.txt"
        p.write_text(
            "https://x/1\nhttps://x/1\nhttps://x/2\n",
            encoding="utf-8",
        )
        store = MyListStore(p, tmp_path / "snaps.json")
        assert store.load_urls() == ["https://x/1", "https://x/2"]

    def test_load_urls_missing_file_returns_empty(self, tmp_path):
        store = MyListStore(tmp_path / "nope.txt", tmp_path / "snaps.json")
        assert store.load_urls() == []

    def test_snapshots_roundtrip(self, tmp_path):
        store = MyListStore(
            tmp_path / "mylist.txt",
            tmp_path / "snaps.json",
        )
        store.save_snapshots({"https://x/1": {"price_jpy": 1000, "status": "active"}})
        loaded = store.load_snapshots()
        assert loaded["https://x/1"]["price_jpy"] == 1000

    def test_load_snapshots_corrupt_file_returns_empty(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        store = MyListStore(tmp_path / "mylist.txt", path)
        assert store.load_snapshots() == {}


class TestDiffSnapshot:
    def _snap(self, **kw):
        defaults = dict(
            url="https://x/1",
            status="active",
            name="A",
            price_jpy=30_000_000,
            address="尼崎市塚口本町１",
            layout="3LDK",
            access="阪急塚口 徒歩5分",
            fetched_at="2026-06-23T00:00:00Z",
        )
        defaults.update(kw)
        return Snapshot(**defaults)

    def test_first_seen_no_diff(self):
        # No prior snapshot → silent baseline.
        assert diff_snapshot(None, self._snap()) == []
        assert diff_snapshot({}, self._snap()) == []

    def test_price_drop_detected(self):
        old = self._snap(price_jpy=30_000_000).to_dict()
        new = self._snap(price_jpy=27_000_000)
        diffs = diff_snapshot(old, new)
        assert any("値下げ" in d for d in diffs)
        assert any("2,700" in d for d in diffs)

    def test_price_increase_detected(self):
        old = self._snap(price_jpy=30_000_000).to_dict()
        new = self._snap(price_jpy=33_000_000)
        diffs = diff_snapshot(old, new)
        assert any("値上げ" in d for d in diffs)

    def test_no_price_change_no_diff(self):
        old = self._snap().to_dict()
        assert diff_snapshot(old, self._snap()) == []

    def test_sold_status_detected(self):
        old = self._snap(status="active").to_dict()
        new = self._snap(status="sold")
        assert any("成約" in d for d in diff_snapshot(old, new))

    def test_removed_status_detected(self):
        old = self._snap(status="active").to_dict()
        new = self._snap(status="removed")
        assert any("掲載終了" in d for d in diff_snapshot(old, new))

    def test_relisted_status_detected(self):
        old = self._snap(status="sold").to_dict()
        new = self._snap(status="active")
        assert any("再開" in d for d in diff_snapshot(old, new))

    def test_layout_change_detected(self):
        old = self._snap(layout="3LDK").to_dict()
        new = self._snap(layout="4LDK")
        assert any("間取り" in d for d in diff_snapshot(old, new))


class TestBuildMylistMessages:
    def _snap(self, **kw):
        d = dict(
            url="https://suumo.jp/x/nc_1/",
            status="active",
            name="リーデンススクエア塚口",
            price_jpy=46_000_000,
            address="兵庫県尼崎市塚口本町6",
            layout="4LDK",
            access="",
            fetched_at="2026-06-23T00:00:00Z",
        )
        d.update(kw)
        return Snapshot(**d)

    def test_empty_changes_returns_empty(self):
        assert build_mylist_messages([]) == []

    def test_message_includes_header_and_fields(self):
        msgs = build_mylist_messages(
            [(self._snap(), ["💴 価格変更: 4,780万円 → 4,600万円 (値下げ ⬇)"])]
        )
        assert len(msgs) == 1
        assert "マイリスト更新" in msgs[0]
        assert "リーデンススクエア塚口" in msgs[0]
        assert "4,600万円" in msgs[0]
        assert "https://suumo.jp/x/nc_1/" in msgs[0]

    def test_chunking_at_listings_per_message(self):
        items = [(self._snap(url=f"https://x/{i}"), ["💴 値下げ"]) for i in range(7)]
        msgs = build_mylist_messages(items)
        # 4 per chunk → 2 messages
        assert len(msgs) == 2
        assert "（続き）" in msgs[1]
