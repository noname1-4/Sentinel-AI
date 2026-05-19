from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from macro_sentinel.models import (
    AppConfig,
    ConfigurationError,
    FetchConfig,
    LLMProviderSettings,
    LLMSettings,
    SUPPORTED_CHANNELS,
    SUPPORTED_LANGUAGES,
    SUPPORTED_LLMS,
    SourceConfig,
)


DEFAULT_LLM_PROVIDERS = {
    "openai": {
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "timeout_seconds": 30,
    },
    "anthropic": {
        "model": "claude-3-5-sonnet-20241022",
        "api_key_env": "ANTHROPIC_API_KEY",
        "timeout_seconds": 30,
    },
    "gemini": {
        "model": "gemini-1.5-flash",
        "api_key_env": "GEMINI_API_KEY",
        "timeout_seconds": 30,
    },
    "groq": {
        "model": "llama3-70b-8192",
        "api_key_env": "GROQ_API_KEY",
        "timeout_seconds": 30,
    },
}


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise ConfigurationError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    config_dir = config_path.parent
    language = str(os.getenv("SENTINEL_LANGUAGE") or _get(raw, "Language", "language", default="vi")).lower()
    active_llm = str(
        os.getenv("SENTINEL_ACTIVE_LLM") or _get(raw, "Active_LLM", "active_llm", default="openai")
    ).lower()
    active_channels_raw = os.getenv("SENTINEL_ACTIVE_CHANNELS")
    active_channels = _as_string_list(
        active_channels_raw
        if active_channels_raw is not None
        else _get(raw, "Active_Channels", "active_channels", default=[])
    )

    if language not in SUPPORTED_LANGUAGES:
        raise ConfigurationError(f"Unsupported language '{language}'. Supported: {sorted(SUPPORTED_LANGUAGES)}")
    if active_llm not in SUPPORTED_LLMS:
        raise ConfigurationError(f"Unsupported LLM '{active_llm}'. Supported: {sorted(SUPPORTED_LLMS)}")

    unknown_channels = sorted(set(active_channels) - SUPPORTED_CHANNELS)
    if unknown_channels:
        raise ConfigurationError(f"Unsupported channels {unknown_channels}. Supported: {sorted(SUPPORTED_CHANNELS)}")

    sources = _parse_sources(_get(raw, "Sources", "sources", default=[]))
    if not sources:
        raise ConfigurationError("At least one source must be configured under Sources.")

    storage_raw = _get(raw, "storage", "Storage", default={}) or {}
    storage_path = str(
        os.getenv("SENTINEL_SQLITE_PATH") or storage_raw.get("sqlite_path", "data/processed_articles.sqlite3")
    )
    storage_path = _resolve_path(storage_path, config_dir)

    fetch_raw = _get(raw, "fetch", "Fetch", default={}) or {}
    fetch_config = FetchConfig(
        request_timeout_seconds=float(fetch_raw.get("request_timeout_seconds", 20)),
        concurrent_requests=int(fetch_raw.get("concurrent_requests", 8)),
        max_entries_per_source=int(fetch_raw.get("max_entries_per_source", 20)),
        max_articles_per_run=int(fetch_raw.get("max_articles_per_run", 10)),
        fetch_article_text=bool(fetch_raw.get("fetch_article_text", False)),
        max_article_chars=int(fetch_raw.get("max_article_chars", 6000)),
        mark_failed_as_processed=bool(fetch_raw.get("mark_failed_as_processed", False)),
        user_agent=str(fetch_raw.get("user_agent", "Macro-Sentinel/1.0")),
    )

    llm_settings = _parse_llm_settings(_get(raw, "llm", "LLM", default={}) or {})
    channels = _get(raw, "channels", "Channels", default={}) or {}
    runtime = _get(raw, "runtime", "Runtime", default={}) or {}
    if os.getenv("SENTINEL_POLL_INTERVAL_SECONDS"):
        runtime["poll_interval_seconds"] = int(os.environ["SENTINEL_POLL_INTERVAL_SECONDS"])

    return AppConfig(
        language=language,
        active_llm=active_llm,
        active_channels=active_channels,
        sources=sources,
        storage_path=storage_path,
        fetch=fetch_config,
        llm=llm_settings,
        channels=channels,
        runtime=runtime,
        config_dir=str(config_dir),
    )


def get_required_env(env_name: str, purpose: str) -> str:
    value = os.getenv(env_name)
    if not value:
        raise ConfigurationError(f"Missing environment variable {env_name} for {purpose}.")
    return value


def get_optional_env(env_name: str) -> str | None:
    return os.getenv(env_name)


def _get(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return default


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip().lower() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    raise ConfigurationError(f"Expected a string list, got {type(value).__name__}.")


def _resolve_path(path_value: str, base_dir: Path) -> str:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return str(path.resolve())


def _parse_sources(raw_sources: Any) -> list[SourceConfig]:
    if not isinstance(raw_sources, list):
        raise ConfigurationError("Sources must be a list of source objects.")

    sources: list[SourceConfig] = []
    for index, item in enumerate(raw_sources, start=1):
        if not isinstance(item, dict):
            raise ConfigurationError(f"Source #{index} must be an object.")

        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        if not name or not url:
            raise ConfigurationError(f"Source #{index} requires both name and url.")

        source_type = str(item.get("type", "rss")).strip().lower()
        if source_type != "rss":
            raise ConfigurationError(f"Source '{name}' has unsupported type '{source_type}'. Only rss is implemented.")

        sources.append(
            SourceConfig(
                name=name,
                url=url,
                type=source_type,
                category=str(item.get("category", "macro")).strip().lower(),
                enabled=bool(item.get("enabled", True)),
            )
        )

    return sources


def _parse_llm_settings(raw_llm: dict[str, Any]) -> LLMSettings:
    providers_raw = dict(DEFAULT_LLM_PROVIDERS)
    providers_raw.update(raw_llm.get("providers", {}) or {})

    providers: dict[str, LLMProviderSettings] = {}
    for provider_name, provider_settings in providers_raw.items():
        provider_name = str(provider_name).lower()
        if provider_name not in SUPPORTED_LLMS:
            continue
        if not isinstance(provider_settings, dict):
            raise ConfigurationError(f"LLM provider '{provider_name}' must be an object.")

        providers[provider_name] = LLMProviderSettings(
            model=str(provider_settings.get("model", DEFAULT_LLM_PROVIDERS[provider_name]["model"])),
            api_key_env=str(provider_settings.get("api_key_env", DEFAULT_LLM_PROVIDERS[provider_name]["api_key_env"])),
            timeout_seconds=float(provider_settings.get("timeout_seconds", 30)),
            base_url=provider_settings.get("base_url"),
            extra={
                key: value
                for key, value in provider_settings.items()
                if key not in {"model", "api_key_env", "timeout_seconds", "base_url"}
            },
        )

    return LLMSettings(
        temperature=float(raw_llm.get("temperature", 0.2)),
        min_output_tokens=int(raw_llm.get("min_output_tokens", 350)),
        max_output_tokens=int(raw_llm.get("max_output_tokens", 700)),
        providers=providers,
    )
