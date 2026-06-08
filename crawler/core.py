import re
import json
import time
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
}

INDONESIAN_MONTHS = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
    "september": 9, "oktober": 10, "november": 11, "desember": 12,
}

INDEX_URL = "https://www.bisnis.com/index"
SEARCH_URL = "https://search.bisnis.com"
SITEMAP_URL = "https://www.bisnis.com/sitemap-news.xml"
URL_DATE_RE = re.compile(r"/read/(\d{8})/")


class BisnisCrawler:
    def __init__(self, delay=1.0, timeout=30):
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get(self, url, retries=3):
        for attempt in range(retries):
            try:
                time.sleep(self.delay)
                r = self.session.get(url, timeout=self.timeout)
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                logger.warning("Attempt %d/%d failed for %s: %s", attempt + 1, retries, url, e)
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        logger.error("All retries exhausted for %s", url)
        return None

    @staticmethod
    def date_from_url(url):
        m = URL_DATE_RE.search(url)
        if m:
            try:
                return datetime.strptime(m.group(1), "%Y%m%d").date()
            except ValueError:
                pass
        return None

    @staticmethod
    def parse_indonesian_date(text):
        if not text:
            return None
        m = re.search(
            r"(\d{1,2})\s+(\w+)\s+(\d{4})(?:\s*\|\s*(\d{1,2}):(\d{2}))?",
            text, re.IGNORECASE,
        )
        if not m:
            return None
        month = INDONESIAN_MONTHS.get(m.group(2).lower())
        if not month:
            return None
        try:
            dt = datetime(
                int(m.group(3)), month, int(m.group(1)),
                int(m.group(4)) if m.group(4) else 0,
                int(m.group(5)) if m.group(5) else 0,
                tzinfo=WIB,
            )
            return dt.isoformat()
        except ValueError:
            return None

    def scrape_article(self, url):
        r = self._get(url)
        if not r:
            return None
        soup = BeautifulSoup(r.text, "lxml")
        title = self._title(soup)
        if not title:
            logger.warning("No title found: %s", url)
            return None
        return {
            "link": url,
            "title": title,
            "content": self._content(soup),
            "published_at": self._date(soup, url),
        }

    def _title(self, soup):
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        og = soup.find("meta", attrs={"property": "og:title"})
        return og.get("content", "").strip() if og else None

    def _date(self, soup, url):
        meta = soup.find("meta", attrs={"property": "article:published_time"})
        if meta and meta.get("content"):
            return meta["content"]

        el = soup.find(attrs={"itemprop": "datePublished"})
        if el:
            v = el.get("datetime") or el.get("content")
            if v:
                return v
            parsed = self.parse_indonesian_date(el.get_text())
            if parsed:
                return parsed

        pattern = re.compile(
            r"\d{1,2}\s+(?:" + "|".join(INDONESIAN_MONTHS) + r")\s+\d{4}", re.IGNORECASE
        )
        for tag in soup.find_all(["div", "span", "time", "p"]):
            t = tag.get_text(strip=True)
            if pattern.search(t) and len(t) < 60:
                parsed = self.parse_indonesian_date(t)
                if parsed:
                    return parsed

        d = self.date_from_url(url)
        if d:
            return datetime(d.year, d.month, d.day, tzinfo=WIB).isoformat()
        return None

    def _content(self, soup):
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        for candidate in [
            soup.find("div", class_=re.compile(r"konten|content|detail|artikel|body", re.I)),
            soup.find("article"),
            soup.find("section", class_=re.compile(r"konten|content|detail", re.I)),
        ]:
            if candidate:
                paras = [
                    p.get_text(" ", strip=True)
                    for p in candidate.find_all("p")
                    if len(p.get_text(strip=True)) > 30
                ]
                if paras:
                    return "\n\n".join(paras)

        start = soup.find("h1") or soup.body
        paras = []
        if start:
            for p in start.find_all_next("p"):
                t = p.get_text(" ", strip=True)
                if len(t) > 40:
                    paras.append(t)
                if len(paras) >= 60:
                    break
        return "\n\n".join(paras)

    def _extract_urls(self, html):
        soup = BeautifulSoup(html, "lxml")
        seen, urls = set(), []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if URL_DATE_RE.search(href):
                full = href if href.startswith("http") else urljoin("https://www.bisnis.com", href)
                if full not in seen:
                    seen.add(full)
                    urls.append(full)
        return urls

    def get_index_page_urls(self, page=1):
        r = self._get(f"{INDEX_URL}?page={page}")
        return self._extract_urls(r.text) if r else []

    def get_total_index_pages(self):
        r = self._get(INDEX_URL)
        if not r:
            return 1
        m = re.search(r"dari\s+(\d+)\s+halaman", r.text, re.IGNORECASE)
        return int(m.group(1)) if m else 1

    def get_search_page_urls(self, page=1, query="Bisnis"):
        r = self._get(f"{SEARCH_URL}/?q={query}&page={page}")
        if not r:
            return []
        soup = BeautifulSoup(r.text, "lxml")
        seen, urls = set(), []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/link?url=" in href:
                real = unquote(href.split("url=", 1)[1])
                if URL_DATE_RE.search(real) and real not in seen:
                    seen.add(real)
                    urls.append(real)
        return urls

    def get_total_search_pages(self, query="Bisnis"):
        r = self._get(f"{SEARCH_URL}/?q={query}&page=1")
        if not r:
            return 1
        nums = re.findall(
            rf"search\.bisnis\.com\?q={re.escape(query)}&amp;page=(\d+)", r.text
        )
        return max((int(n) for n in nums), default=1)

    def find_start_page(self, end, query, total_pages):
        lo, hi = 1, total_pages
        while lo < hi:
            mid = (lo + hi) // 2
            urls = self.get_search_page_urls(mid, query)
            dates = [d for d in (self.date_from_url(u) for u in urls) if d]
            if not dates or min(dates) > end:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def iter_search_urls(self, start, end, query="Bisnis"):
        total = self.get_total_search_pages(query)
        start_page = self.find_start_page(end, query, total)
        logger.info("Binary search: starting from page %d / %d", start_page, total)

        seen = set()
        for page in range(start_page, total + 1):
            urls = self.get_search_page_urls(page, query)
            if not urls:
                return
            dates = [d for d in (self.date_from_url(u) for u in urls) if d]
            for url in urls:
                d = self.date_from_url(url)
                if d and start <= d <= end and url not in seen:
                    seen.add(url)
                    yield url
            if dates and max(dates) < start:
                return

    def get_sitemap_articles(self):
        r = self._get(SITEMAP_URL)
        if not r:
            return []
        articles = []
        try:
            root = ET.fromstring(r.content)
            sm = "http://www.sitemaps.org/schemas/sitemap/0.9"
            ns = "http://www.google.com/schemas/sitemap-news/0.9"
            for u in root.findall(f"{{{sm}}}url"):
                loc = u.findtext(f"{{{sm}}}loc")
                if loc:
                    articles.append({
                        "url": loc,
                        "title": u.findtext(f"{{{ns}}}news/{{{ns}}}title"),
                        "published_at": u.findtext(f"{{{ns}}}news/{{{ns}}}publication_date"),
                    })
        except ET.ParseError as e:
            logger.error("Sitemap parse error: %s", e)
        return articles

    @staticmethod
    def save_json(articles, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        logger.info("Saved %d articles to %s", len(articles), path)
