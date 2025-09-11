import re
import time
from typing import List, Dict, Optional
from urllib.parse import urljoin, quote

import requests
from bs4 import BeautifulSoup
import json
import os
from pathlib import Path


BASE = "https://www.rad-ar.or.jp/siori/english/"
SEARCH_URL = urljoin(BASE, "search")


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "en,ja;q=0.9,ko;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Referer": BASE.rstrip("/") + "/",
}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    return s


def _abs(url: str) -> str:
    return urljoin(BASE, url)


def fetch_search_html(keyword: str) -> str:
    # The site accepts a 'w' parameter with plaintext keyword
    params = {"w": keyword}
    s = _session()
    res = s.get(SEARCH_URL, params=params, timeout=20)
    res.raise_for_status()
    return res.text


def parse_result_links(html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    links: List[str] = []
    for a in soup.select('a[href*="search/result?n="]'):
        href = a.get("href")
        if not href:
            continue
        full = _abs(href)
        if full not in links:
            links.append(full)
    return links


def fetch_detail(url: str) -> str:
    s = _session()
    res = s.get(url, timeout=20)
    res.raise_for_status()
    return res.text


def parse_detail(html: str, page_url: str) -> Dict:
    soup = BeautifulSoup(html, "lxml")
    brand = (soup.select_one("h1") or {}).get_text(strip=True) if soup.select_one("h1") else ""
    # Company: first external link (non rad-ar) near header area
    company = ""
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("http") and "rad-ar.or.jp" not in href:
            company = a.get_text(strip=True)
            break

    # Route (Internal/External/Injection etc.)
    route = ""
    for el in soup.find_all(text=True):
        t = (el or "").strip()
        if re.search(r"\b(Internal|External|Injection|Self-injection)\b", t, re.I):
            route = t
            break

    # Revised
    revised = ""
    m = re.search(r"Revised:\s*([^<\n]+)", soup.get_text("\n"), re.I)
    if m:
        revised = m.group(1).strip()

    # Table rows
    row_map = {}
    for tr in soup.select("table tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) >= 2:
            key = re.sub(r"\s+", " ", cells[0].get_text(strip=True))
            val = cells[1].get_text(strip=True)
            row_map[key] = val

    active = row_map.get("Active ingredient:") or row_map.get("Active ingredient") or ""
    dosage = row_map.get("Dosage form:") or row_map.get("Dosage form") or ""

    # Word doc link if present
    doc_url = ""
    a_doc = soup.find("a", href=lambda h: isinstance(h, str) and h.lower().endswith(".doc"))
    if a_doc and a_doc.get("href"):
        href = a_doc["href"].strip()
        doc_url = _abs(href) if href.startswith("/") else href

    return {
        "page_url": page_url,
        "brand": brand,
        "company": company,
        "route": route,
        "revised": revised,
        "active_ingredient": active,
        "dosage_form": dosage,
        "doc_url": doc_url,
    }


def radar_search(keyword: str, limit: int = 10) -> List[Dict]:
    html = fetch_search_html(keyword)
    links = parse_result_links(html)
    # Fallback: discover via external search engines if site search yields nothing
    if not links:
        links = discover_detail_links(keyword)
    results: List[Dict] = []
    for url in links[: max(1, limit)]:
        try:
            detail_html = fetch_detail(url)
            item = parse_detail(detail_html, url)
            results.append(item)
            time.sleep(0.3)
        except Exception:
            continue
    return results


# -----------------------------
# Local cache (JSON) utilities
# -----------------------------

DATA_DIR = Path("data/radar")


def _safe_slug(keyword: str) -> str:
    kw = (keyword or "").strip()
    if not kw:
        return "query"
    # Keep simple ascii/digit/_- only; others replaced by '_'
    out = []
    for ch in kw.lower():
        if ch.isalnum() or ch in ("_", "-"):
            out.append(ch)
        elif ch.isspace():
            out.append("_")
        else:
            out.append("_")
    slug = "".join(out).strip("_") or "query"
    return slug


def _local_json_path(keyword: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f"{_safe_slug(keyword)}.json"


def save_search_to_json(keyword: str, items: List[Dict]) -> Path:
    path = _local_json_path(keyword)
    payload = {"query": keyword, "count": len(items), "items": items}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def load_local_json(keyword: str) -> Optional[Dict]:
    path = _local_json_path(keyword)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return data
    except Exception:
        return None
    return None


def radar_search_cached(keyword: str, limit: int = 10) -> List[Dict]:
    # Try local first
    local = load_local_json(keyword)
    if local and local.get("items"):
        return local["items"][: max(1, limit)]
    # Fallback to live fetch then save
    items = radar_search(keyword, limit=limit)
    try:
        save_search_to_json(keyword, items)
    except Exception:
        pass
    return items


# -----------------------------
# Fallback discovery via web search
# -----------------------------

def _extract_detail_links_from_html(html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    urls: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "rad-ar.or.jp/siori/english/search/result?n=" in href:
            # Clean tracking params
            urls.append(href.split("&")[0])
    # Normalize and dedupe
    out: List[str] = []
    seen = set()
    for u in urls:
        if "/search/result?n=" in u:
            if not u.startswith("http"):
                u = _abs(u)
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out


def discover_detail_links(keyword: str) -> List[str]:
    s = _session()
    # DuckDuckGo HTML
    try:
        q = f"site:rad-ar.or.jp/siori/english/ search/result?n= {keyword}"
        res = s.get("https://duckduckgo.com/html/", params={"q": q}, timeout=20)
        res.raise_for_status()
        links = _extract_detail_links_from_html(res.text)
        if links:
            return links
    except Exception:
        pass
    # Bing fallback
    try:
        q = f"site:rad-ar.or.jp/siori/english/ \"search/result?n=\" {keyword}"
        res = s.get("https://www.bing.com/search", params={"q": q}, timeout=20)
        res.raise_for_status()
        links = _extract_detail_links_from_html(res.text)
        if links:
            return links
    except Exception:
        pass
    return []


