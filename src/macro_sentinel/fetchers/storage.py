from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from macro_sentinel.models import Article


TRACKING_PARAMS = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref"}


class ProcessedURLStore:
    def __init__(self, sqlite_path: str) -> None:
        self.sqlite_path = sqlite_path

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    async def filter_new(self, articles: list[Article]) -> list[Article]:
        return await asyncio.to_thread(self._filter_new_sync, articles)

    async def mark_processed(self, article: Article, status: str) -> None:
        await asyncio.to_thread(self._mark_processed_sync, article, status)

    def _connect(self) -> sqlite3.Connection:
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.sqlite_path, timeout=10)
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def _initialize_sync(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_articles (
                    normalized_url TEXT PRIMARY KEY,
                    original_url TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_processed_articles_processed_at
                ON processed_articles(processed_at)
                """
            )

    def _filter_new_sync(self, articles: list[Article]) -> list[Article]:
        if not articles:
            return []

        normalized_urls = list({normalize_url(article.url) for article in articles if article.url})
        if not normalized_urls:
            return []

        seen: set[str] = set()
        with self._connect() as connection:
            for offset in range(0, len(normalized_urls), 500):
                batch = normalized_urls[offset : offset + 500]
                placeholders = ",".join("?" for _ in batch)
                rows = connection.execute(
                    f"SELECT normalized_url FROM processed_articles WHERE normalized_url IN ({placeholders})",
                    batch,
                ).fetchall()
                seen.update(row[0] for row in rows)

        new_articles: list[Article] = []
        emitted: set[str] = set()
        for article in articles:
            normalized = normalize_url(article.url)
            if normalized not in seen and normalized not in emitted:
                new_articles.append(article)
                emitted.add(normalized)
        return new_articles

    def _mark_processed_sync(self, article: Article, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO processed_articles (
                    normalized_url,
                    original_url,
                    source_name,
                    title,
                    status,
                    processed_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(normalized_url) DO UPDATE SET
                    original_url = excluded.original_url,
                    source_name = excluded.source_name,
                    title = excluded.title,
                    status = excluded.status,
                    processed_at = excluded.processed_at
                """,
                (
                    normalize_url(article.url),
                    article.url,
                    article.source_name,
                    article.title,
                    status,
                    now,
                ),
            )


def normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    ]
    normalized_path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            normalized_path,
            urlencode(query_pairs, doseq=True),
            "",
        )
    )
