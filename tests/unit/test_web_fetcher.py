"""Tests for Step C: web_fetcher + datasheet-collect integration."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "tools")

import web_fetcher  # noqa: E402


def test_search_and_fetch_returns_empty_on_network_failure(tmp_path: Path) -> None:
    """web_fetcher must never raise — soft-fail on network error."""
    with patch("web_fetcher._search_duckduckgo", side_effect=ConnectionError("offline")):
        result = web_fetcher.search_and_fetch(["STM32F407 datasheet"], tmp_path)
    assert result["saved_count"] == 0
    assert len(result["errors"]) == 1
    assert "search failed" in result["errors"][0]["reason"]
    assert result["queries"] == ["STM32F407 datasheet"]


def test_search_and_fetch_saves_results(tmp_path: Path) -> None:
    """When search returns hits and downloads succeed, saved_count > 0."""
    fake_hits = [
        {"url": "https://example.com/stm32-ref-manual.pdf", "title": "STM32 Reference Manual"},
        {"url": "https://example.com/stm32-datasheet.pdf", "title": "STM32 Datasheet"},
    ]
    fake_content = b"%PDF-1.4 fake pdf content"

    with patch("web_fetcher._search_duckduckgo", return_value=fake_hits):
        with patch("web_fetcher._download", return_value=(tmp_path / "fake.pdf", "application/pdf")):
            result = web_fetcher.search_and_fetch(["STM32F407 reference manual"], tmp_path, max_files=5)
    assert result["saved_count"] == 2
    assert len(result["results"]) == 2
    assert result["results"][0]["title"] == "STM32 Reference Manual"


def test_search_and_fetch_respects_max_files(tmp_path: Path) -> None:
    fake_hits = [{"url": f"https://example.com/{i}.pdf", "title": f"doc {i}"} for i in range(10)]
    with patch("web_fetcher._search_duckduckgo", return_value=fake_hits):
        with patch("web_fetcher._download", return_value=(tmp_path / "fake.pdf", "application/pdf")):
            result = web_fetcher.search_and_fetch(["query"], tmp_path, max_files=3)
    assert result["saved_count"] == 3


def test_search_and_fetch_dedupes_urls(tmp_path: Path) -> None:
    same_url = "https://example.com/datasheet.pdf"
    fake_hits = [{"url": same_url, "title": "doc1"}]
    with patch("web_fetcher._search_duckduckgo", return_value=fake_hits):
        with patch("web_fetcher._download", return_value=(tmp_path / "fake.pdf", "application/pdf")):
            result = web_fetcher.search_and_fetch(["q1", "q2", "q3"], tmp_path, max_files=10)
    assert result["saved_count"] == 1


def test_parse_duckduckgo_results_extracts_url_and_title() -> None:
    html_text = """
    <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fstm32.pdf&rut=abc">STM32 Reference</a>
    <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fesp32.pdf&rut=def">ESP32 Manual</a>
    """
    results = web_fetcher._parse_duckduckgo_results(html_text)
    assert len(results) == 2
    assert results[0]["url"] == "https://example.com/stm32.pdf"
    assert results[0]["title"] == "STM32 Reference"
    assert results[1]["url"] == "https://example.com/esp32.pdf"


def test_resolve_ddg_redirect_unwraps_uddg_param() -> None:
    raw = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdatasheet.pdf&rut=xyz"
    assert web_fetcher._resolve_ddg_redirect(raw) == "https://example.com/datasheet.pdf"


def test_resolve_ddg_redirect_passes_through_non_ddg_url() -> None:
    raw = "https://direct.example.com/file.pdf"
    assert web_fetcher._resolve_ddg_redirect(raw) == raw


def test_safe_filename_replaces_unsafe_chars() -> None:
    name = web_fetcher._safe_filename("https://x.com/a b/c:d?e=f.pdf", ".pdf")
    # No spaces, colons, or question marks
    assert " " not in name
    assert ":" not in name
    assert "?" not in name
    assert name.endswith(".pdf")


def test_ext_for_url_pdf() -> None:
    assert web_fetcher._ext_for_url("https://x.com/doc.pdf", "application/pdf") == ".pdf"
    assert web_fetcher._ext_for_url("https://x.com/doc.html", "text/html") == ".html"
    assert web_fetcher._ext_for_url("https://x.com/doc", "application/pdf") == ".pdf"
    assert web_fetcher._ext_for_url("https://x.com/doc", "text/html") == ".html"
    assert web_fetcher._ext_for_url("https://x.com/doc", "application/octet-stream") == ".bin"
