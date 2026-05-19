from __future__ import annotations

import asyncio
import os
import sqlite3
from contextlib import asynccontextmanager
from contextlib import suppress
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from macro_sentinel.app import run_loop
from macro_sentinel.core.config import load_config
from macro_sentinel.fetchers import ProcessedURLStore
from macro_sentinel.models import AppConfig, ConfigurationError


DEFAULT_CONFIG_PATH = "/app/config.yaml"
DEFAULT_STATIC_DIR = "/app/static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    config_path = _config_path()
    config = load_config(config_path)
    await ProcessedURLStore(config.storage_path).initialize()
    bot_task = None
    if _run_bot_in_api():
        bot_task = asyncio.create_task(run_loop(config_path))

    try:
        yield
    finally:
        if bot_task:
            bot_task.cancel()
            with suppress(asyncio.CancelledError):
                await bot_task


app = FastAPI(
    title="Sentinel-AI V2 API",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, Any]:
    config = _load_config_or_500()
    database = Path(config.storage_path)
    return {
        "status": "ok",
        "service": "sentinel-api",
        "active_llm": config.active_llm,
        "database": {
            "path": str(database),
            "exists": database.exists(),
        },
    }


@app.get("/api/config")
def read_config() -> dict[str, Any]:
    config = _load_config_or_500()
    return {
        "language": config.language,
        "active_llm": config.active_llm,
        "active_channels": config.active_channels,
        "poll_interval_seconds": int(config.runtime.get("poll_interval_seconds", 300)),
        "storage_path": config.storage_path,
        "sources": [
            {
                "name": source.name,
                "category": source.category,
                "enabled": source.enabled,
                "type": source.type,
            }
            for source in config.sources
        ],
    }


@app.get("/api/stats")
def read_stats() -> dict[str, Any]:
    config = _load_config_or_500()
    database = Path(config.storage_path)
    if not database.exists():
        return _empty_stats(database)

    try:
        with _connect(database) as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END), 0) AS sent,
                    COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS failed,
                    COALESCE(
                        SUM(CASE WHEN status = 'analyzed_no_channels' THEN 1 ELSE 0 END),
                        0
                    ) AS analyzed_no_channels,
                    MAX(processed_at) AS last_processed_at
                FROM processed_articles
                """
            ).fetchone()
    except sqlite3.OperationalError as exc:
        if _is_missing_table(exc):
            return _empty_stats(database)
        raise HTTPException(status_code=500, detail=f"SQLite error: {exc}") from exc

    return {
        "database_path": str(database),
        "total": int(row["total"]),
        "sent": int(row["sent"]),
        "failed": int(row["failed"]),
        "analyzed_no_channels": int(row["analyzed_no_channels"]),
        "last_processed_at": row["last_processed_at"],
    }


@app.get("/api/articles")
def read_articles(
    limit: Annotated[int, Query(ge=1, le=250)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    config = _load_config_or_500()
    database = Path(config.storage_path)
    if not database.exists():
        return {"items": [], "limit": limit, "offset": offset}

    try:
        with _connect(database) as connection:
            rows = connection.execute(
                """
                SELECT
                    normalized_url,
                    original_url,
                    source_name,
                    title,
                    status,
                    processed_at
                FROM processed_articles
                ORDER BY processed_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
    except sqlite3.OperationalError as exc:
        if _is_missing_table(exc):
            return {"items": [], "limit": limit, "offset": offset}
        raise HTTPException(status_code=500, detail=f"SQLite error: {exc}") from exc

    return {
        "items": [dict(row) for row in rows],
        "limit": limit,
        "offset": offset,
    }


def _load_config() -> AppConfig:
    return load_config(_config_path())


def _config_path() -> str:
    return os.getenv("SENTINEL_CONFIG", DEFAULT_CONFIG_PATH)


def _load_config_or_500() -> AppConfig:
    try:
        return _load_config()
    except ConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _empty_stats(database: Path) -> dict[str, Any]:
    return {
        "database_path": str(database),
        "total": 0,
        "sent": 0,
        "failed": 0,
        "analyzed_no_channels": 0,
        "last_processed_at": None,
    }


def _is_missing_table(exc: sqlite3.OperationalError) -> bool:
    return "no such table" in str(exc).lower()


def _cors_origins() -> list[str]:
    origins = os.getenv("SENTINEL_CORS_ORIGINS", "http://localhost:8080,http://localhost:5173")
    return [origin.strip() for origin in origins.split(",") if origin.strip()]


def _run_bot_in_api() -> bool:
    return os.getenv("SENTINEL_RUN_BOT_IN_API", "").strip().lower() in {"1", "true", "yes", "on"}


def _mount_static_app() -> None:
    static_dir = Path(os.getenv("SENTINEL_STATIC_DIR", DEFAULT_STATIC_DIR))
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


_mount_static_app()
