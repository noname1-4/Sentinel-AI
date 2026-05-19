from __future__ import annotations

from typing import Any

import aiohttp

from macro_sentinel.core.config import get_required_env
from macro_sentinel.models import NotificationError, SendResult
from macro_sentinel.notifiers.base import BaseNotifier
from macro_sentinel.notifiers.formatting import split_message


class DiscordNotifier(BaseNotifier):
    channel = "discord"

    def __init__(self, settings: dict[str, Any]) -> None:
        webhook_url_env = str(settings.get("webhook_url_env", "DISCORD_WEBHOOK_URL"))
        self.webhook_url = get_required_env(webhook_url_env, "Discord webhook")
        self.username = str(settings.get("username", "Macro-Sentinel"))

    async def send(self, message: str) -> SendResult:
        async with aiohttp.ClientSession() as session:
            for chunk in split_message(message, 1900):
                payload = {"content": chunk, "username": self.username}
                async with session.post(self.webhook_url, json=payload) as response:
                    body = await response.text()
                    if response.status >= 400:
                        raise NotificationError(f"Discord rejected message: HTTP {response.status} {body}")
        return SendResult(channel=self.channel, success=True)
