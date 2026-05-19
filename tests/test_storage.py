from __future__ import annotations

from macro_sentinel.fetchers.storage import normalize_url


def test_normalize_url_removes_tracking_params() -> None:
    url = "https://EXAMPLE.com/news/?utm_source=x&b=1&fbclid=abc#section"

    assert normalize_url(url) == "https://example.com/news?b=1"
