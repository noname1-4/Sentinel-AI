from __future__ import annotations

import re

from macro_sentinel.models import AnalysisResult


def format_notification(result: AnalysisResult) -> str:
    article = result.article
    return f"{result.markdown}\n\nSource: {article.source_name}\n{article.url}"


def to_telegram_markdown_v2(markdown: str) -> str:
    lines = []
    for line in markdown.splitlines():
        if line.startswith("### "):
            lines.append(f"*{_escape_telegram(line[4:].strip())}*")
        else:
            lines.append(_convert_bold_segments(line))
    return "\n".join(lines)


def split_message(message: str, limit: int) -> list[str]:
    chunks: list[str] = []
    remaining = message.strip()
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < int(limit * 0.5):
            split_at = remaining.rfind(" ", 0, limit)
        if split_at < int(limit * 0.5):
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _convert_bold_segments(line: str) -> str:
    parts = re.split(r"(\*\*.*?\*\*)", line)
    output = []
    for part in parts:
        if part.startswith("**") and part.endswith("**") and len(part) >= 4:
            output.append(f"*{_escape_telegram(part[2:-2])}*")
        else:
            output.append(_escape_telegram(part))
    return "".join(output)


def _escape_telegram(value: str) -> str:
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!])", r"\\\1", value)
