"""Web fetcher for the datasheet-collect workflow stage.

Performs search queries and downloads datasheets / HTML pages to a local
out_dir. Designed to fail soft: any network error returns an empty result
so the workflow can degrade to LLM task package fallback instead of blocking.

No API key required — uses DuckDuckGo HTML scraping via urllib.
"""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

USER_AGENT = "hardware-butler/1.0 (+https://github.com/yihang56666-sketch/NextBoard)"
MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024
DOWNLOAD_TIMEOUT_S = 15
SEARCH_TIMEOUT_S = 10
MAX_RESULTS_PER_QUERY = 5


def search_and_fetch(queries: list[str], out_dir: Path, *, max_files: int = 5) -> dict[str, Any]:
    """Run search queries and download top results to out_dir.

    Returns dict with queries, results (list of saved files), saved_count,
    errors, and a note. Never raises — all failures are captured in errors.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for query in queries:
        if len(saved) >= max_files:
            break
        try:
            hits = _search_duckduckgo(query)
        except Exception as exc:  # noqa: BLE001
            errors.append({"query": query, "reason": f"search failed: {exc}"})
            continue
        for hit in hits:
            if len(saved) >= max_files:
                break
            url = hit.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            try:
                saved_path, content_type = _download(url, out_dir)
                saved.append({
                    "query": query,
                    "url": url,
                    "title": hit.get("title", ""),
                    "saved_path": str(saved_path),
                    "content_type": content_type,
                })
            except Exception as exc:  # noqa: BLE001
                errors.append({"query": query, "url": url, "reason": f"download failed: {exc}"})

    return {
        "queries": queries,
        "results": saved,
        "saved_count": len(saved),
        "errors": errors,
        "note": "DuckDuckGo HTML scrape; no API key; soft-fail on network error",
    }


def _search_duckduckgo(query: str) -> list[dict[str, str]]:
    """Scrape DuckDuckGo HTML search results. Returns list of {url, title}."""
    url = "https://html.duckduckgo.com/html/"
    data = urllib.parse.urlencode({"q": query, "kl": "us-en"}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=SEARCH_TIMEOUT_S) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    return _parse_duckduckgo_results(text)[:MAX_RESULTS_PER_QUERY]


def _parse_duckduckgo_results(html_text: str) -> list[dict[str, str]]:
    """Extract result URLs + titles from DuckDuckGo HTML page."""
    results: list[dict[str, str]] = []
    for match in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html_text, re.DOTALL):
        raw_url = match.group(1)
        title_html = match.group(2)
        title = html.unescape(re.sub(r"<[^>]+>", "", title_html)).strip()
        parsed_url = _resolve_ddg_redirect(raw_url)
        if parsed_url and title:
            results.append({"url": parsed_url, "title": title})
    return results


def _resolve_ddg_redirect(raw_url: str) -> str:
    """DuckDuckGo wraps result URLs in //duckduckgo.com/l/?uddg=... — unwrap."""
    if "uddg=" in raw_url:
        parsed = urllib.parse.urlparse(raw_url)
        params = urllib.parse.parse_qs(parsed.query)
        if "uddg" in params and params["uddg"]:
            return urllib.parse.unquote(params["uddg"][0])
    return raw_url


def _download(url: str, out_dir: Path) -> tuple[Path, str]:
    """Download a URL to out_dir, return (saved_path, content_type)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_S) as resp:
        data = resp.read(MAX_DOWNLOAD_BYTES + 1)
        if len(data) > MAX_DOWNLOAD_BYTES:
            raise ValueError(f"file too large (> {MAX_DOWNLOAD_BYTES} bytes)")
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        ext = _ext_for_url(url, content_type)
        filename = _safe_filename(url, ext)
        out_path = out_dir / filename
        out_path.write_bytes(data)
        return out_path, content_type


def _ext_for_url(url: str, content_type: str) -> str:
    path = urllib.parse.urlparse(url).path.lower()
    for ext in (".pdf", ".html", ".htm", ".txt"):
        if path.endswith(ext):
            return ext
    if "pdf" in content_type.lower():
        return ".pdf"
    if "html" in content_type.lower():
        return ".html"
    return ".bin"


def _safe_filename(url: str, ext: str) -> str:
    """Build a filesystem-safe filename from URL."""
    parsed = urllib.parse.urlparse(url)
    base = parsed.path.rsplit("/", 1)[-1]
    if not base or len(base) > 80:
        base = urllib.parse.quote_plus(url)[:60]
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    if not safe.endswith(ext):
        safe = safe + ext
    return safe
