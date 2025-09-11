import os
import re
import time
import random
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup


MATSUKIYO_SEARCH = "https://www.matsukiyococokara-online.com/store/catalogsearch/result/"
YAHOO_SHOP_SEARCH = "https://shopping.yahoo.co.jp/search/"


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9,ko;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


CATEGORY_TO_QUERIES = {
    "acetaminophen": ["アセトアミノフェン", "カロナール", "タイレノール"],
    "antidiarrheal": ["下痢止め", "ロペラミド", "整腸剤"],
    "antacid": ["胃薬", "制酸薬", "H2ブロッカー"],
    "simethicone": ["シメチコン", "ガス たまる 薬"],
    "antihistamine": ["抗ヒスタミン", "かゆみ止め", "アレルギー 市販薬"],
    "ors": ["経口補水液", "OS-1", "オーエスワン"],
    "lozenge": ["トローチ", "のど飴 医薬品"],
    "decongestant": ["点鼻薬 血管収縮", "鼻づまり 薬"],
    "burngel": ["やけど ジェル", "やけど 軟膏"],
    "emollient": ["保湿 クリーム", "保湿 乳液 敏感肌"],
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def slugify(text: str) -> str:
    text = re.sub(r"[\s/\\]+", "-", text.strip())
    text = re.sub(r"[^a-zA-Z0-9\-\u3040-\u30FF\u4E00-\u9FFF]", "", text)
    return text[:60] or "item"


def fetch(url: str) -> requests.Response:
    resp = SESSION.get(url, timeout=15, allow_redirects=True)
    resp.raise_for_status()
    return resp


def parse_product_links(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.select("a[href*='/store/catalog/product/view/']"):
        href = a.get("href")
        if href and href not in links:
            links.append(href)
    return links[:10]


def extract_best_image_url(product_html: str) -> tuple[str, str]:
    soup = BeautifulSoup(product_html, "lxml")
    title = soup.find("h1")
    title_text = title.get_text(strip=True) if title else "product"

    # 1) og:image
    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        return title_text, og.get("content")

    # 2) product gallery
    img = soup.select_one("img[src*='/media/']")
    if img and img.get("src"):
        return title_text, img.get("src")

    # 3) fallback: any https image
    img2 = soup.find("img")
    if img2 and img2.get("src"):
        return title_text, img2.get("src")

    return title_text, ""


def download_image(url: str, out_path: Path, referer: str | None = None) -> bool:
    if not url:
        return False
    try:
        headers = dict(SESSION.headers)
        if referer:
            headers["Referer"] = referer
        r = SESSION.get(url, headers=headers, timeout=20, allow_redirects=True)
        r.raise_for_status()
        out_path.write_bytes(r.content)
        return True
    except Exception:
        return False


def crawl_category(cat: str, out_dir: Path, queries: list[str]) -> int:
    ensure_dir(out_dir)
    saved = 0
    for q in queries:
        params = {"search_keyword": q, "layout": "1"}
        url = f"{MATSUKIYO_SEARCH}?{urllib.parse.urlencode(params)}"
        try:
            res = fetch(url)
        except Exception:
            continue
        links = parse_product_links(res.text)
        for link in links[:5]:
            try:
                pr = fetch(link)
            except Exception:
                continue
            title, img_url = extract_best_image_url(pr.text)
            if not img_url:
                continue
            slug = slugify(title)
            ext = ".jpg"
            if ".png" in img_url.lower():
                ext = ".png"
            out_file = out_dir / f"{slug}{ext}"
            if out_file.exists():
                continue
            if download_image(img_url, out_file, referer=link):
                saved += 1
                time.sleep(random.uniform(0.8, 1.6))
        time.sleep(random.uniform(1.0, 2.0))
        # Yahoo Shopping fallback if nothing saved for this query
        if saved == 0:
            try:
                y_params = {"p": q, "tab_ex": "commerce", "ei": "UTF-8"}
                y_url = f"{YAHOO_SHOP_SEARCH}?{urllib.parse.urlencode(y_params)}"
                y_res = fetch(y_url)
                y_soup = BeautifulSoup(y_res.text, "lxml")
                imgs = []
                for im in y_soup.select("img"):
                    src = im.get("src") or ""
                    alt = im.get("alt") or ""
                    if not src:
                        continue
                    if "yimg.jp" in src and ("item" in src or src.endswith((".jpg", ".jpeg", ".png"))):
                        imgs.append((alt, src))
                for alt, src in imgs[:6]:
                    slug = slugify(alt or q)
                    ext = ".jpg"
                    lo = src.lower()
                    if lo.endswith(".png"):
                        ext = ".png"
                    out_file = out_dir / f"{slug}{ext}"
                    if out_file.exists():
                        continue
                    if download_image(src, out_file, referer=y_url):
                        saved += 1
                        time.sleep(random.uniform(0.6, 1.2))
            except Exception:
                pass
    return saved


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "static" / "otc" / "jp"
    total = 0
    for cat, queries in CATEGORY_TO_QUERIES.items():
        out_dir = root / cat
        count = crawl_category(cat, out_dir, queries)
        print(f"[{cat}] saved: {count}")
        total += count
    print(f"TOTAL saved: {total}")


if __name__ == "__main__":
    main()


