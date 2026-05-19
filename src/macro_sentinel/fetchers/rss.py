from __future__ import annotations

import asyncio
from collections.abc import Iterable

import aiohttp
import feedparser
from bs4 import BeautifulSoup
from loguru import logger

from macro_sentinel.models import AppConfig, Article, FetchError, SourceConfig


class NewsFetcher:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    async def fetch_articles(self) -> list[Article]:
        enabled_sources = [source for source in self.config.sources if source.enabled]
        if not enabled_sources:
            logger.warning("No enabled sources configured.")
            return []

        timeout = aiohttp.ClientTimeout(total=self.config.fetch.request_timeout_seconds)
        headers = {"User-Agent": self.config.fetch.user_agent}
        semaphore = asyncio.Semaphore(self.config.fetch.concurrent_requests)

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            tasks = [self._fetch_source(session, semaphore, source) for source in enabled_sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        articles: list[Article] = []
        for source, result in zip(enabled_sources, results):
            if isinstance(result, Exception):
                logger.exception("Failed to fetch source '{}': {}", source.name, result)
                continue
            articles.extend(result)

        return articles

    async def _fetch_source(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        source: SourceConfig,
    ) -> list[Article]:
        if source.type != "rss":
            raise FetchError(f"Unsupported source type '{source.type}' for {source.name}.")

        body = await self._get_text(session, semaphore, source.url)
        feed = feedparser.parse(body)
        if getattr(feed, "bozo", False):
            logger.warning("RSS parser warning for '{}': {}", source.name, getattr(feed, "bozo_exception", "unknown"))

        entries = list(getattr(feed, "entries", []))[: self.config.fetch.max_entries_per_source]
        articles = [article for article in (self._entry_to_article(source, entry) for entry in entries) if article]

        if self.config.fetch.fetch_article_text and articles:
            await self._enrich_with_article_text(session, semaphore, articles)

        logger.info("Fetched {} candidate articles from {}.", len(articles), source.name)
        return articles

    async def _get_text(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        url: str,
    ) -> str:
        async with semaphore:
            async with session.get(url) as response:
                response.raise_for_status()
                return await response.text(errors="replace")

    def _entry_to_article(self, source: SourceConfig, entry: object) -> Article | None:
        link = str(_entry_get(entry, "link") or _entry_get(entry, "id") or "").strip()
        title = _html_to_text(str(_entry_get(entry, "title") or "")).strip()
        if not link or not title:
            return None

        description = self._extract_entry_text(entry)
        published_at = str(_entry_get(entry, "published") or _entry_get(entry, "updated") or "").strip() or None

        return Article(
            source_name=source.name,
            source_category=source.category,
            title=title,
            url=link,
            description=description,
            raw_text=description,
            published_at=published_at,
        )

    def _extract_entry_text(self, entry: object) -> str:
        chunks: list[str] = []
        content = _entry_get(entry, "content")
        if isinstance(content, Iterable) and not isinstance(content, (str, bytes, dict)):
            for item in content:
                value = _entry_get(item, "value")
                if value:
                    chunks.append(str(value))

        summary = _entry_get(entry, "summary") or _entry_get(entry, "description")
        if summary:
            chunks.append(str(summary))

        return _html_to_text(" ".join(chunks))

    async def _enrich_with_article_text(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        articles: list[Article],
    ) -> None:
        tasks = [self._safe_fetch_article_body(session, semaphore, article) for article in articles]
        bodies = await asyncio.gather(*tasks, return_exceptions=False)
        for article, body in zip(articles, bodies):
            if body and len(body) > len(article.raw_text):
                article.raw_text = body

    async def _safe_fetch_article_body(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        article: Article,
    ) -> str:
        try:
            html = await self._get_text(session, semaphore, article.url)
        except Exception as exc:
            logger.debug("Could not fetch article body for {}: {}", article.url, exc)
            return ""

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav", "aside"]):
            tag.decompose()

        candidates = soup.select("article p") or soup.select("main p") or soup.select("p")
        text = " ".join(paragraph.get_text(" ", strip=True) for paragraph in candidates)
        return _clean_whitespace(text)


def _entry_get(entry: object, key: str) -> object | None:
    if isinstance(entry, dict):
        return entry.get(key)
    return getattr(entry, key, None)


def _html_to_text(value: str) -> str:
    return _clean_whitespace(BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True))


def _clean_whitespace(value: str) -> str:
    return " ".join((value or "").split())
