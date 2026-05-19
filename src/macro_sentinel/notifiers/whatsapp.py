from __future__ import annotations

from typing import Any

import aiohttp
from loguru import logger

from macro_sentinel.core.config import get_optional_env
from macro_sentinel.models import ConfigurationError, NotificationError, SendResult
from macro_sentinel.notifiers.base import BaseNotifier


class WhatsAppWebhookNotifier(BaseNotifier):
    channel = "whatsapp"

    def __init__(self, settings: dict[str, Any]) -> None:
        self.dry_run = bool(settings.get("dry_run", True))
        self.provider = str(settings.get("provider", "generic_webhook"))
        webhook_url_env = str(settings.get("webhook_url_env", "WHATSAPP_WEBHOOK_URL"))
        bearer_token_env = str(settings.get("bearer_token_env", "WHATSAPP_BEARER_TOKEN"))
        self.webhook_url = get_optional_env(webhook_url_env)
        self.bearer_token = get_optional_env(bearer_token_env)

        if not self.dry_run and not self.webhook_url:
            raise ConfigurationError(f"Missing WhatsApp webhook URL. Set {webhook_url_env} or enable dry_run.")

    async def send(self, message: str) -> SendResult:
        if self.dry_run:
            logger.info("WhatsApp dry_run enabled; message prepared but not sent.")
            return SendResult(channel=self.channel, success=True, detail="dry_run")

        headers = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        payload = {"provider": self.provider, "text": message}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(self.webhook_url, json=payload) as response:
                body = await response.text()
                if response.status >= 400:
                    raise NotificationError(f"WhatsApp webhook rejected message: HTTP {response.status} {body}")
        return SendResult(channel=self.channel, success=True)
