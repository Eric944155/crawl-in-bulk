import io
import re
from dataclasses import dataclass
from typing import Iterable, List, Set, Tuple
from urllib.parse import urljoin, urlparse

import pandas as pd
import validators
from bs4 import BeautifulSoup
from email_validator import EmailNotValidError, validate_email


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# Matches standard emails, but we will run every match through validate_email.
EMAIL_REGEX = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}",
    re.IGNORECASE,
)

OBFUSCATION_PATTERNS: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(r"\s*\[\s*at\s*\]\s*", re.I), "@"),
    (re.compile(r"\s*\(\s*at\s*\)\s*", re.I), "@"),
    (re.compile(r"\s+at\s+", re.I), "@"),
    (re.compile(r"\s*@\s*"), "@"),
    (re.compile(r"\s*\[\s*dot\s*\]\s*", re.I), "."),
    (re.compile(r"\s*\(\s*dot\s*\)\s*", re.I), "."),
    (re.compile(r"\s+dot\s+", re.I), "."),
    (re.compile(r"\s*\[\s*d0t\s*\]\s*", re.I), "."),
    (re.compile(r"\s*\(\s*d0t\s*\)\s*", re.I), "."),
    (re.compile(r"\s+d0t\s+", re.I), "."),
    (re.compile(r"\s*\[\s*underscore\s*\]\s*", re.I), "_"),
    (re.compile(r"\s*\(\s*underscore\s*\)\s*", re.I), "_"),
    (re.compile(r"\s+underscore\s+", re.I), "_"),
    (re.compile(r"\s*\[\s*dash\s*\]\s*", re.I), "-"),
    (re.compile(r"\s*\(\s*dash\s*\)\s*", re.I), "-"),
    (re.compile(r"\s+dash\s+", re.I), "-"),
    (re.compile(r"\s*\[\s*plus\s*\]\s*", re.I), "+"),
    (re.compile(r"\s*\(\s*plus\s*\)\s*", re.I), "+"),
    (re.compile(r"\s+plus\s+", re.I), "+"),
    (re.compile(r"【\s*at\s*】", re.I), "@"),
    (re.compile(r"【\s*dot\s*】", re.I), "."),
    (re.compile(r"\s*＠\s*"), "@"),
    (re.compile(r"\s*（\s*at\s*）", re.I), "@"),
    (re.compile(r"\s*（\s*dot\s*）", re.I), "."),
    (re.compile(r"\s*点\s*", re.I), "."),
)

SOCIAL_PATTERNS = {
    "facebook": re.compile(r"facebook\.com/(?!share)"),
    "twitter": re.compile(r"(?:twitter|x)\.com/"),
    "linkedin": re.compile(r"linkedin\.com/"),
    "instagram": re.compile(r"instagram\.com/"),
    "youtube": re.compile(r"youtu(?:\.be|be\.com)/"),
    "tiktok": re.compile(r"tiktok\.com/"),
    "telegram": re.compile(r"t\.me/"),
    "whatsapp": re.compile(r"(?:wa\.me|api\.whatsapp\.com)/"),
    "wechat": re.compile(r"weixin\.qq\.com/"),
}

CONTACT_KEYWORDS = [
    "contact",
    "about",
    "support",
    "impressum",
    "legal",
    "connect",
    "team",
    "company",
    "联系",
    "联系我们",
    "关于",
    "支持",
    "团队",
]


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def is_valid_url(url: str) -> bool:
    try:
        return validators.url(url)
    except Exception:
        return False


def clean_and_validate_email(raw_email: str) -> str | None:
    candidate = (raw_email or "").strip()
    if not candidate:
        return None
    try:
        result = validate_email(candidate, check_deliverability=False)
        return result.email
    except EmailNotValidError:
        return None


def deobfuscate(text: str) -> str:
    result = text
    for pattern, repl in OBFUSCATION_PATTERNS:
        result = pattern.sub(repl, result)
    return result


def extract_emails_from_text(text: str) -> Set[str]:
    normalized = deobfuscate(text)
    emails = set()
    for match in EMAIL_REGEX.findall(normalized):
        validated = clean_and_validate_email(match)
        if validated:
            emails.add(validated)
    return emails


def extract_emails_from_soup(soup: BeautifulSoup, base_url: str) -> Set[str]:
    emails: Set[str] = set()

    # mailto links
    for tag in soup.select("a[href^=mailto]"):
        href = tag.get("href", "")
        addr = href.split(":", 1)[-1].split("?", 1)[0]
        emails.update(extract_emails_from_text(addr))

    # attributes that may contain emails
    interesting_attrs = ("content", "value", "data-email", "data-mail", "title", "alt")
    for tag in soup.find_all(attrs={attr: True for attr in interesting_attrs}):
        for attr in interesting_attrs:
            val = tag.attrs.get(attr)
            if isinstance(val, str):
                emails.update(extract_emails_from_text(val))

    # text nodes
    for chunk in soup.stripped_strings:
        if "@" in chunk or " at " in chunk.lower():
            emails.update(extract_emails_from_text(chunk))

    # scripts / styles
    for tag in soup.find_all(["script", "style", "noscript"]):
        content = tag.string or ""
        if "@" in content or " at " in content.lower():
            emails.update(extract_emails_from_text(content))

    return emails


def extract_social_links(soup: BeautifulSoup) -> dict:
    links_by_platform: dict[str, Set[str]] = {}
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        for platform, pattern in SOCIAL_PATTERNS.items():
            if pattern.search(href):
                links_by_platform.setdefault(platform, set()).add(href)
    return {k: sorted(v) for k, v in links_by_platform.items()}


def discover_candidate_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    candidates: List[str] = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(base_url, href)
        text = (tag.get_text() or "").lower()
        score = sum(keyword in href.lower() or keyword in text for keyword in CONTACT_KEYWORDS)
        if score > 0 and absolute not in candidates:
            candidates.append(absolute)
    return candidates


def load_website_list(source) -> pd.DataFrame:
    """
    Accepts uploaded file, path-like or raw string containing URLs separated by newline.
    Returns DataFrame with a deduplicated 'url' column.
    """
    urls: Set[str] = set()
    if isinstance(source, pd.DataFrame):
        for col in source.columns:
            for value in source[col]:
                candidate = normalize_url(str(value))
                if is_valid_url(candidate):
                    urls.add(candidate)
    elif isinstance(source, io.StringIO):
        source.seek(0)
        for line in source:
            candidate = normalize_url(line)
            if is_valid_url(candidate):
                urls.add(candidate)
    elif hasattr(source, "read"):
        content = source.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
        for line in content.splitlines():
            candidate = normalize_url(line)
            if is_valid_url(candidate):
                urls.add(candidate)
    elif isinstance(source, str):
        for line in source.replace(",", "\n").splitlines():
            candidate = normalize_url(line)
            if is_valid_url(candidate):
                urls.add(candidate)
    else:
        raise ValueError("不支持的输入类型，请提供CSV/文本文件或换行分隔的URL字符串。")

    if not urls:
        raise ValueError("未发现有效网址，请检查输入。")

    return pd.DataFrame({"url": sorted(urls)})


@dataclass
class PageResult:
    url: str
    emails: Set[str]
    social_links: dict
    visited_pages: int
    errors: List[str]

