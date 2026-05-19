from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from loguru import logger

from macro_sentinel.analysis import AnalysisEngine
from macro_sentinel.core.config import load_config
from macro_sentinel.core.logging import configure_logging
from macro_sentinel.fetchers import NewsFetcher, ProcessedURLStore
from macro_sentinel.llm_clients import build_llm_client
from macro_sentinel.models import Article, MacroSentinelError
from macro_sentinel.notifiers import build_notifiers, format_notification


async def run_once(config_path: str, configure_logger: bool = True) -> None:
    config = load_config(config_path)
    if configure_logger:
        configure_logging(
            level_name=str(config.runtime.get("log_level", "INFO")),
            log_file=str(config.runtime.get("log_file", "logs/macro.log")),
        )

    store = ProcessedURLStore(config.storage_path)
    await store.initialize()

    fetcher = NewsFetcher(config)
    articles = await fetcher.fetch_articles()
    new_articles = await store.filter_new(_sort_articles(articles))
    new_articles = new_articles[: config.fetch.max_articles_per_run]

    if not new_articles:
        logger.info("No new articles found.")
        return

    logger.info("Processing {} new articles.", len(new_articles))
    llm_client = build_llm_client(config)
    analysis_engine = AnalysisEngine(config, llm_client)
    notifiers = build_notifiers(config)
    if not notifiers:
        logger.warning("No active notification channels configured; analyses will be marked without sending.")

    for article in new_articles:
        try:
            result = await analysis_engine.analyze(article)
            message = format_notification(result)
            status = await _notify_all(notifiers, message) if notifiers else "analyzed_no_channels"
            await store.mark_processed(article, status=status)
            logger.info("Processed article: {} [{}]", article.title, status)
        except Exception as exc:
            logger.exception("Failed to process article '{}': {}", article.title, exc)
            if config.fetch.mark_failed_as_processed:
                await store.mark_processed(article, status="failed")


async def run_loop(config_path: str, interval_seconds: int | None = None) -> None:
    config = load_config(config_path)
    configure_logging(
        level_name=str(config.runtime.get("log_level", "INFO")),
        log_file=str(config.runtime.get("log_file", "logs/macro.log")),
    )
    interval = interval_seconds or int(config.runtime.get("poll_interval_seconds", 300))
    logger.info("Macro-Sentinel started with {} second polling.", interval)

    while True:
        try:
            await run_once(config_path, configure_logger=False)
        except MacroSentinelError as exc:
            logger.error("Configuration/runtime error: {}", exc)
        except Exception as exc:
            logger.exception("Unexpected runtime failure: {}", exc)
        await asyncio.sleep(interval)


async def _notify_all(notifiers: list[object], message: str) -> str:
    tasks = [notifier.send(message) for notifier in notifiers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    successes = 0
    failures = 0

    for result in results:
        if isinstance(result, Exception):
            failures += 1
            logger.error("Notification failed: {}", result)
        elif getattr(result, "success", False):
            successes += 1
        else:
            failures += 1

    if successes and failures:
        return "partially_sent"
    if successes:
        return "sent"
    return "notification_failed"


def _sort_articles(articles: list[Article]) -> list[Article]:
    return sorted(articles, key=lambda article: article.published_at or "", reverse=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Macro-Sentinel macroeconomic and crypto news analysis bot.")
    parser.add_argument("--config", default=str(Path("config.yaml")), help="Path to config.yaml.")
    parser.add_argument("--loop", action="store_true", help="Continuously poll sources.")
    parser.add_argument("--interval", type=int, default=None, help="Override polling interval in seconds.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.loop:
        asyncio.run(run_loop(args.config, args.interval))
    else:
        asyncio.run(run_once(args.config))


if __name__ == "__main__":
    main()
