"""LINE notification connector (LINE Messaging API).

Sends push (or broadcast) messages to LINE via the Messaging API.

Why the Messaging API and not LINE Notify?
    LINE Notify was discontinued on 2025-03-31, so this connector targets
    the LINE Messaging API instead. You need a Messaging API channel on a
    LINE Official Account, then:
      - HDOS_LINE_CHANNEL_TOKEN : the channel access token
      - HDOS_LINE_TARGET_ID     : the destination userId / groupId / roomId
                                  (leave blank to broadcast to all friends)

API reference:
    POST https://api.line.me/v2/bot/message/push       (to a specific target)
    POST https://api.line.me/v2/bot/message/broadcast  (to every friend)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.connectors.base import BaseConnector, ConnectorResult

logger = logging.getLogger(__name__)

_PUSH_URL = "https://api.line.me/v2/bot/message/push"
_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"

# LINE limits: max 5 message objects per request, 5000 chars per text message.
_MAX_MESSAGES_PER_REQUEST = 5
_MAX_TEXT_LENGTH = 5000


class LineNotifyConnector(BaseConnector):
    """Push text messages to LINE via the Messaging API."""

    def __init__(
        self,
        channel_token: str = "",
        target_id: str = "",
    ) -> None:
        self.channel_token = channel_token
        self.target_id = target_id

    @property
    def name(self) -> str:
        return "LINE Messaging API"

    async def fetch(
        self,
        messages: list[str] | None = None,
        text: str = "",
        **kwargs: Any,
    ) -> ConnectorResult:
        """Send one or more text messages to LINE.

        Parameters
        ----------
        messages : list[str] | None
            A list of text message bodies. Each becomes one LINE message.
        text : str
            Convenience for sending a single message.
        """
        bodies = list(messages or [])
        if text:
            bodies.append(text)
        bodies = [b for b in (s.strip() for s in bodies) if b]

        if not bodies:
            return ConnectorResult(
                success=False,
                source=self.name,
                errors=["送信するメッセージがありません"],
            )

        if not self.channel_token:
            return ConnectorResult(
                success=False,
                source=self.name,
                errors=[
                    "LINEチャネルアクセストークンが未設定です (HDOS_LINE_CHANNEL_TOKEN)",
                ],
            )

        # Truncate over-long messages defensively.
        bodies = [_truncate(b, _MAX_TEXT_LENGTH) for b in bodies]

        use_broadcast = not self.target_id
        url = _BROADCAST_URL if use_broadcast else _PUSH_URL
        headers = {
            "Authorization": f"Bearer {self.channel_token}",
            "Content-Type": "application/json",
        }

        sent = 0
        errors: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                for batch in _chunk(bodies, _MAX_MESSAGES_PER_REQUEST):
                    payload: dict[str, Any] = {
                        "messages": [{"type": "text", "text": b} for b in batch],
                    }
                    if not use_broadcast:
                        payload["to"] = self.target_id

                    resp = await client.post(
                        url,
                        headers=headers,
                        json=payload,
                    )
                    if resp.status_code == 200:
                        sent += len(batch)
                    else:
                        errors.append(f"LINE送信失敗 HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:  # noqa: BLE001 - surface as connector error
            logger.error("LINE push error: %s", exc)
            return ConnectorResult(
                success=False,
                source=self.name,
                errors=[f"LINE送信エラー: {exc!s}"],
            )

        return ConnectorResult(
            success=sent > 0,
            source=self.name,
            data={
                "sent": sent,
                "mode": "broadcast" if use_broadcast else "push",
            },
            errors=errors,
        )


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]
