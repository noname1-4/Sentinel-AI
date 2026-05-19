from __future__ import annotations

from macro_sentinel.models import AppConfig, ConfigurationError
from macro_sentinel.notifiers.base import BaseNotifier
from macro_sentinel.notifiers.discord import DiscordNotifier
from macro_sentinel.notifiers.telegram import TelegramNotifier
from macro_sentinel.notifiers.whatsapp import WhatsAppWebhookNotifier


def build_notifiers(config: AppConfig) -> list[BaseNotifier]:
    notifiers: list[BaseNotifier] = []
    for channel in config.active_channels:
        settings = config.channels.get(channel, {})
        if channel == "telegram":
            notifiers.append(TelegramNotifier(settings))
        elif channel == "discord":
            notifiers.append(DiscordNotifier(settings))
        elif channel == "whatsapp":
            notifiers.append(WhatsAppWebhookNotifier(settings))
        else:
            raise ConfigurationError(f"Unsupported channel: {channel}")
    return notifiers
