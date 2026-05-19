from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


SUPPORTED_CHANNELS = {"telegram", "discord", "whatsapp"}
SUPPORTED_LANGUAGES = {"vi", "en", "fr", "it", "es", "de", "zh"}
SUPPORTED_LLMS = {"openai", "anthropic", "gemini", "groq"}


class MacroSentinelError(Exception):
    """Base exception for Macro-Sentinel."""


class ConfigurationError(MacroSentinelError):
    """Raised when configuration or credentials are invalid."""


class FetchError(MacroSentinelError):
    """Raised when a news source cannot be fetched or parsed."""


class LLMProviderError(MacroSentinelError):
    """Raised when an LLM provider request fails."""


class NotificationError(MacroSentinelError):
    """Raised when a notification channel rejects a message."""


@dataclass(frozen=True)
class SourceConfig:
    name: str
    url: str
    type: str = "rss"
    category: str = "macro"
    enabled: bool = True


@dataclass(frozen=True)
class FetchConfig:
    request_timeout_seconds: float = 20.0
    concurrent_requests: int = 8
    max_entries_per_source: int = 20
    max_articles_per_run: int = 10
    fetch_article_text: bool = False
    max_article_chars: int = 6000
    mark_failed_as_processed: bool = False
    user_agent: str = "Macro-Sentinel/1.0"


@dataclass(frozen=True)
class LLMProviderSettings:
    model: str
    api_key_env: str
    timeout_seconds: float = 30.0
    base_url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMSettings:
    temperature: float = 0.2
    min_output_tokens: int = 350
    max_output_tokens: int = 700
    providers: dict[str, LLMProviderSettings] = field(default_factory=dict)


@dataclass(frozen=True)
class AppConfig:
    language: str
    active_llm: str
    active_channels: list[str]
    sources: list[SourceConfig]
    storage_path: str
    fetch: FetchConfig
    llm: LLMSettings
    channels: dict[str, Any]
    runtime: dict[str, Any]
    config_dir: str


@dataclass
class Article:
    source_name: str
    source_category: str
    title: str
    url: str
    description: str = ""
    raw_text: str = ""
    published_at: str | None = None

    @property
    def text_for_analysis(self) -> str:
        return (self.raw_text or self.description or "").strip()


@dataclass(frozen=True)
class AnalysisResult:
    article: Article
    markdown: str
    language: str
    provider: str
    model: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class SendResult:
    channel: str
    success: bool
    detail: str = ""
