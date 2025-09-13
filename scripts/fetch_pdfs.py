import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
import concurrent.futures as cf
import requests
from bs4 import BeautifulSoup


ALLOWED_DOMAINS = [
    "jrc.or.jp",      # 日本赤十字社
    "fdma.go.jp",     # 消防庁
    "mhlw.go.jp",     # 厚生労働省
    "pmda.go.jp",     # PMDA
    "rad-ar.or.jp",   # RAD-AR
]

SEED_URLS = [
    # 日本赤十字社: 応急手当・災害救護関連
    "https://www.jrc.or.jp/study/kind/emergency/",
    "https://www.jrc.or.jp/activity/disaster/",
    # 消防庁: 応急手当・救急受診関連
    "https://www.fdma.go.jp/publication/",
    "https://www.fdma.go.jp/mission/safety/index.html",
    # 厚生労働省: 健康・医療情報
    "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/kenkou_iryou/iryou/",
    "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/kenkou_iryou/",
    # PMDA: 患者向け医薬品等情報
    "https://www.pmda.go.jp/safety/infoservices/forpatients/otc/",
    "https://www.pmda.go.jp/patients/medicine/",
    # RAD-AR: くすりのしおり
    "https://www.rad-ar.or.jp/siori/",
]

KEYWORDS = [
    # 응급/처치/수진
    "応急", "救急", "応急手当", "救急受診", "手当", "救護", "蘇生",
    # 의약/복용/부작용
    "医薬品", "くすり", "薬", "服用", "副作用",
    # 증상/상황
    "発熱", "咳", "呼吸困難", "アレルギー", "虫刺され", "やけど", "出血",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9,ko;q=0.8",
}


def same_allowed_domain(url: str) -> bool:
    netloc = urlparse(url).netloc
    return any(netloc.endswith(d) for d in ALLOWED_DOMAINS)


def normalize_link(base: str, href: str) -> str | None:
    if not href:
        return None
    if href.startswith("javascript:") or href.startswith("mailto:"):
        return None
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return urljoin(base, href)
    if not href.startswith("http"):
        return urljoin(base, href)
    return href


def fetch_html(session: requests.Session, url: str, timeout: int = 15) -> tuple[str, str]:
    try:
        res = session.get(url, timeout=timeout)
        ctype = res.headers.get("Content-Type", "")
        if res.status_code == 200 and "text/html" in ctype:
            return url, res.text
    except Exception:
        pass
    return url, ""


def extract_links(base_url: str, html: str) -> list[str]:
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = normalize_link(base_url, a["href"])
        if not href:
            continue
        if same_allowed_domain(href):
            links.append(href)
    # de-dupe
    seen = set()
    uniq: list[str] = []
    for u in links:
        if u in seen:
            continue
        seen.add(u)
        uniq.append(u)
    return uniq


def extract_pdf_links(base_url: str, html: str) -> list[tuple[str, str]]:
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    results: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = normalize_link(base_url, a["href"])
        if not href or not href.lower().endswith(".pdf"):
            continue
        title = a.get_text(strip=True) or href.split("/")[-1]
        if any(k in title for k in KEYWORDS) or any(k in href for k in KEYWORDS):
            results.append((title, href))
    # de-dupe by URL
    seen = set()
    uniq: list[tuple[str, str]] = []
    for t, u in results:
        if u in seen:
            continue
        seen.add(u)
        uniq.append((t, u))
    return uniq


def crawl_seed(session: requests.Session, seed: str, max_pages: int = 120, max_pdfs: int = 40) -> list[tuple[str, str]]:
    queue: list[str] = [seed]
    visited: set[str] = set()
    found_pdfs: list[tuple[str, str]] = []

    with cf.ThreadPoolExecutor(max_workers=6) as executor:
        while queue and len(visited) < max_pages and len(found_pdfs) < max_pdfs:
            batch: list[str] = []
            while queue and len(batch) < 8:
                url = queue.pop(0)
                if url in visited:
                    continue
                visited.add(url)
                batch.append(url)

            futures = {executor.submit(fetch_html, session, u): u for u in batch}
            for fut in cf.as_completed(futures):
                base = futures[fut]
                html = ""
                try:
                    _, html = fut.result()
                except Exception:
                    pass
                if not html:
                    continue

                # collect PDFs
                for t, link in extract_pdf_links(base, html):
                    found_pdfs.append((t, link))
                    if len(found_pdfs) >= max_pdfs:
                        break
                if len(found_pdfs) >= max_pdfs:
                    break

                # enqueue next links
                for v in extract_links(base, html):
                    if v not in visited and (len(visited) + len(queue)) < max_pages:
                        queue.append(v)

    # de-dupe
    seen = set()
    uniq: list[tuple[str, str]] = []
    for t, u in found_pdfs:
        if u in seen:
            continue
        seen.add(u)
        uniq.append((t, u))
    return uniq


def download_pdf(session: requests.Session, title: str, url: str, out_dir: Path) -> str | None:
    try:
        res = session.get(url, timeout=30)
        res.raise_for_status()
        # sanitize filename (allow basic JP chars)
        safe = re.sub(r"[^\w\-一-龯ぁ-んァ-ン]+", "_", title)[:90]
        if not safe:
            safe = url.split("/")[-1].split(".pdf")[0]
        path = out_dir / f"{safe}.pdf"
        with open(path, "wb") as f:
            f.write(res.content)
        # filter out tiny files (likely not useful)
        if path.stat().st_size < 8_000:
            try:
                path.unlink()
            except Exception:
                pass
            return None
        return str(path)
    except Exception:
        return None


def main() -> None:
    out_dir = Path("data/rag_data")
    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update(HEADERS)

    all_pdfs: list[tuple[str, str]] = []
    for seed in SEED_URLS:
        try:
            found = crawl_seed(session, seed)
            all_pdfs.extend(found)
        except Exception:
            continue

    # global de-dupe (site crawl)
    seen = set()
    unique: list[tuple[str, str]] = []
    for t, u in all_pdfs:
        if u in seen:
            continue
        seen.add(u)
        unique.append((t, u))

    # limit to avoid over-fetch (site crawl)
    unique = unique[:35]

    paths: list[str] = []
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(download_pdf, session, t, u, out_dir) for t, u in unique]
        for fut in cf.as_completed(futures):
            p = fut.result()
            if p:
                paths.append(p)

    # -----------------------------
    # Fallback: search engine discovery
    # -----------------------------
    def extract_pdf_links_from_search(html: str, domain: str) -> list[str]:
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".pdf" not in href:
                continue
            if domain in href:
                urls.append(href)
        # normalize
        out: list[str] = []
        seen2 = set()
        for u in urls:
            if not u.startswith("http"):
                continue
            if u in seen2:
                continue
            seen2.add(u)
            out.append(u)
        return out

    def search_discover(domain: str, keyword: str) -> list[str]:
        urls: list[str] = []
        try:
            q = f"site:{domain} {keyword} filetype:pdf"
            r = session.get("https://duckduckgo.com/html/", params={"q": q}, timeout=20)
            if r.status_code == 200:
                urls.extend(extract_pdf_links_from_search(r.text, domain))
        except Exception:
            pass
        try:
            q = f"site:{domain} {keyword} filetype:pdf"
            r = session.get("https://www.bing.com/search", params={"q": q}, timeout=20)
            if r.status_code == 200:
                urls.extend(extract_pdf_links_from_search(r.text, domain))
        except Exception:
            pass
        # de-dupe
        seen3 = set()
        out: list[str] = []
        for u in urls:
            if u in seen3:
                continue
            seen3.add(u)
            out.append(u)
        return out

    # domains to search
    domains = ALLOWED_DOMAINS
    search_keywords = [
        "応急手当", "救急受診", "救急", "救護", "医薬品", "くすり", "副作用", "服用", "熱中症", "止血", "やけど",
    ]

    discovered: list[tuple[str, str]] = []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        futs = []
        for d in domains:
            for kw in search_keywords:
                futs.append(ex.submit(search_discover, d, kw))
        for fut in cf.as_completed(futs):
            try:
                urls = fut.result()
            except Exception:
                urls = []
            for u in urls:
                # title from filename
                title = u.split("/")[-1]
                if title.lower().endswith(".pdf"):
                    title = title[:-4]
                discovered.append((title, u))

    # de-dupe against already downloaded/queued
    already = set(unique)
    seen_urls = set(u for _, u in unique)
    extra: list[tuple[str, str]] = []
    for t, u in discovered:
        if u in seen_urls:
            continue
        seen_urls.add(u)
        extra.append((t, u))

    # cap extra
    extra = extra[:30]

    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        futures = [ex.submit(download_pdf, session, t, u, out_dir) for t, u in extra]
        for fut in cf.as_completed(futures):
            p = fut.result()
            if p:
                paths.append(p)

    print(f"FOUND:{len(all_pdfs)} UNIQ:{len(unique)} DOWNLOADED:{len(paths)}")
    for p in paths:
        print(p)


if __name__ == "__main__":
    main()


