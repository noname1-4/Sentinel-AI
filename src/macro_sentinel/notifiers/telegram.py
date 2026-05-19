from __future__ import annotations

from typing import Any

import aiohttp

from macro_sentinel.core.config import get_required_env
from macro_sentinel.models import NotificationError, SendResult
from macro_sentinel.notifiers.base import BaseNotifier
from macro_sentinel.notifiers.formatting import split_message, to_telegram_markdown_v2


class TelegramNotifier(BaseNotifier):
    channel = "telegram"
    _api_url_template = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, settings: dict[str, Any]) -> None:
        bot_token_env = str(settings.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))
        chat_id_env = str(settings.get("chat_id_env", "TELEGRAM_CHAT_ID"))
        self.bot_token = get_required_env(bot_token_env, "Telegram bot token")
        self.chat_id = get_required_env(chat_id_env, "Telegram chat id")

    async def send(self, message: str) -> SendResult:
        url = self._api_url_template.format(token=self.bot_token)
        async with aiohttp.ClientSession() as session:
            for chunk in split_message(to_telegram_markdown_v2(message), 3900):
                payload = {
                    "chat_id": self.chat_id,
                    "text": chunk,
                    "parse_mode": "MarkdownV2",
                    "disable_web_page_preview": True,
                }
                async with session.post(url, json=payload) as response:
                    body = await response.text()
                    if response.status >= 400:
                        raise NotificationError(f"Telegram rejected message: HTTP {response.status} {body}")
        return SendResult(channel=self.channel, success=True)
