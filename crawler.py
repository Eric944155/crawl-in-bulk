from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict
from typing import Iterable, List
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from utils import (
    DEFAULT_HEADERS,
    PageResult,
    discover_candidate_links,
    extract_emails_from_soup,
    extract_social_links,
    normalize_url,
)


def _build_session(timeout: int = 12) -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session.timeout = timeout
    return session


def _fetch_html(session: requests.Session, url: str, timeout: int = 12) -> tuple[str | None, str | None]:
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
        if response.status_code >= 400:
            return None, f"{url}: HTTP {response.status_code}"
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return None, f"{url}: 非HTML内容（{content_type or '未知类型'}）"
        response.encoding = response.apparent_encoding
        return response.text, None
    except requests.RequestException as exc:
        return None, f"{url}: {exc}"
    except Exception as exc:  # noqa: BLE001
        return None, f"{url}: {exc}"


def _same_domain(target: str, base: str) -> bool:
    try:
        t_netloc = urlparse(target).netloc.lower()
        b_netloc = urlparse(base).netloc.lower()
        if t_netloc.startswith("www."):
            t_netloc = t_netloc[4:]
        if b_netloc.startswith("www."):
            b_netloc = b_netloc[4:]
        return t_netloc == b_netloc and bool(t_netloc)
    except Exception:
        return False


def crawl_single_site(
    url: str,
    max_pages: int = 5,
    delay: float = 1.0,
    timeout: int = 12,
) -> PageResult:
    session = _build_session(timeout=timeout)
    start_url = normalize_url(url)
    queue: deque[str] = deque([start_url])
    visited: set[str] = set()
    collected_emails: set[str] = set()
    social_links: dict[str, set[str]] = {}
    errors: List[str] = []
    pages_processed = 0

    while queue and pages_processed < max_pages:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        html, error = _fetch_html(session, current, timeout=timeout)
        if error:
            errors.append(error)
            continue
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        pages_processed += 1

        collected_emails.update(extract_emails_from_soup(soup, start_url))

        social = extract_social_links(soup)
        for platform, links in social.items():
            social_links.setdefault(platform, set()).update(links)

        for candidate in discover_candidate_links(soup, current):
            if candidate not in visited and _same_domain(candidate, start_url):
                queue.append(candidate)

        if delay:
            time.sleep(delay)

    return PageResult(
        url=start_url,
        emails=collected_emails,
        social_links={k: sorted(v) for k, v in social_links.items()},
        visited_pages=pages_processed,
        errors=errors,
    )


def crawl_contacts(
    websites: Iterable[str] | pd.DataFrame,
    max_pages_per_site: int = 5,
    delay: float = 1.0,
    timeout: int = 12,
) -> pd.DataFrame:
    if isinstance(websites, pd.DataFrame):
        url_iterable = websites["url"].tolist() if "url" in websites.columns else websites.iloc[:, 0].tolist()
    else:
        url_iterable = list(websites)

    results: List[PageResult] = []
    for url in url_iterable:
        site_url = normalize_url(url)
        result = crawl_single_site(site_url, max_pages=max_pages_per_site, delay=delay, timeout=timeout)
        results.append(result)

    rows = []
    for result in results:
        row = asdict(result)
        row["emails"] = sorted(result.emails)
        row["social_links"] = result.social_links
        row["error"] = "\n".join(result.errors)
        row.pop("errors", None)
        rows.append(row)

    return pd.DataFrame(rows)
