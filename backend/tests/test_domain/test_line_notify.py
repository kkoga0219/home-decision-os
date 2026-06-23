"""Tests for the LINE notification connector (no network)."""

import asyncio

from app.connectors.line_notify import LineNotifyConnector


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestLineNotifyGuards:
    def test_no_token_fails_cleanly(self):
        c = LineNotifyConnector(channel_token="")
        result = _run(c.fetch(text="hello"))
        assert not result.success
        assert any("トークン" in e for e in result.errors)

    def test_no_messages_fails(self):
        c = LineNotifyConnector(channel_token="tok")
        result = _run(c.fetch())
        assert not result.success
        assert any("メッセージ" in e for e in result.errors)

    def test_blank_messages_filtered(self):
        c = LineNotifyConnector(channel_token="tok")
        result = _run(c.fetch(messages=["  ", ""]))
        assert not result.success
