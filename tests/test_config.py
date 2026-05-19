from __future__ import annotations

from macro_sentinel.core.config import load_config


def test_load_config_supports_enterprise_keys(tmp_path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
Language: en
Active_LLM: groq
Active_Channels: []
storage:
  sqlite_path: data/articles.sqlite3
Sources:
  - name: Example Feed
    url: https://example.com/rss
    type: rss
    category: macro
    enabled: true
""",
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.language == "en"
    assert config.active_llm == "groq"
    assert config.active_channels == []
    assert len(config.sources) == 1
    assert config.storage_path.endswith("data/articles.sqlite3")
