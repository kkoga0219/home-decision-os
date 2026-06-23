"""Tests for the new-listing alert state store."""

from app.services.alert_state import AlertState, listing_key


class TestListingKey:
    def test_prefers_url(self):
        ls = {"url": "https://suumo.jp/ms/chuko/x/nc_1/", "name": "A"}
        assert listing_key(ls) == "https://suumo.jp/ms/chuko/x/nc_1/"

    def test_hash_fallback_when_no_url(self):
        ls = {"source": "homes", "name": "A", "price_jpy": 1000}
        key = listing_key(ls)
        assert key.startswith("hash:")
        # deterministic
        assert key == listing_key(dict(ls))

    def test_different_listings_differ(self):
        a = listing_key({"source": "homes", "name": "A", "price_jpy": 1})
        b = listing_key({"source": "homes", "name": "B", "price_jpy": 1})
        assert a != b


class TestAlertState:
    def test_new_then_marked(self):
        st = AlertState()
        ls = {"url": "u1"}
        assert st.is_new(ls)
        st.mark(ls)
        assert not st.is_new(ls)
        assert len(st) == 1

    def test_mark_is_idempotent(self):
        st = AlertState()
        ls = {"url": "u1"}
        st.mark(ls)
        st.mark(ls)
        assert len(st) == 1

    def test_save_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "state.json"
        st = AlertState()
        st.mark({"url": "u1"})
        st.mark({"url": "u2"})
        st.save(path)

        loaded = AlertState.load(path)
        assert len(loaded) == 2
        assert not loaded.is_new({"url": "u1"})
        assert loaded.is_new({"url": "u3"})

    def test_load_missing_file(self, tmp_path):
        st = AlertState.load(tmp_path / "nope.json")
        assert len(st) == 0

    def test_load_corrupt_file(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        st = AlertState.load(path)
        assert len(st) == 0

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "nested" / "dir" / "state.json"
        st = AlertState()
        st.mark({"url": "u1"})
        st.save(path)
        assert path.exists()
