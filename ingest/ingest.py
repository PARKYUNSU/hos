import os
import re
import pathlib
import requests
import yaml
from bs4 import BeautifulSoup
from pdfminer.high_level import extract_text


ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "jp"
PASSAGE_DIR = ROOT / "data" / "passages" / "jp"
SEED_FILE = ROOT / "ingest" / "seeds_jp.yml"


def ensure_dirs():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PASSAGE_DIR.mkdir(parents=True, exist_ok=True)


def load_seeds():
    with open(SEED_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def fetch(url: str) -> bytes:
    headers = {"User-Agent": f"hos-emergency-bot/0.1 ({os.getenv('CONTACT_EMAIL','')})"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.content


def extract_links(html: str, base_url: str, patterns):
    soup = BeautifulSoup(html, "lxml")
    anchors = soup.select("a[href]")
    urls = set()
    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        if href.startswith("http"):
            url = href
        elif href.startswith("/"):
            url = base_url.rstrip("/") + href
        else:
            continue
        if any(p in a.get_text() or p in url for p in patterns):
            urls.add(url)
    return list(urls)


def save_raw(content: bytes, name_hint: str):
    path = RAW_DIR / name_hint
    path.write_bytes(content)
    return path


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    # remove scripts/styles
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def pdf_to_text(pdf_bytes: bytes) -> str:
    tmp = RAW_DIR / "_tmp.pdf"
    tmp.write_bytes(pdf_bytes)
    try:
        return extract_text(str(tmp))
    finally:
        if tmp.exists():
            tmp.unlink()


def chunk_text(text: str, max_len: int = 1000, overlap: int = 150):
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    buf = ""
    for p in paragraphs:
        if len(buf) + len(p) + 2 <= max_len:
            buf = (buf + "\n\n" + p).strip()
        else:
            if buf:
                chunks.append(buf)
                buf = p
    if buf:
        chunks.append(buf)
    # simple overlap
    out = []
    for c in chunks:
        if out:
            tail = out[-1][-overlap:]
            out.append((tail + "\n" + c)[: max_len + overlap])
        else:
            out.append(c[: max_len])
    return out


def write_passages(chunks, base_name: str):
    for i, c in enumerate(chunks):
        p = PASSAGE_DIR / f"{base_name}_{i:03d}.txt"
        p.write_text(c, encoding="utf-8")


def run():
    ensure_dirs()
    seeds = load_seeds()
    for s in seeds:
        base = s["url"].rstrip("/")
        patterns = s.get("patterns", [])
        try:
            html = fetch(base).decode("utf-8", errors="ignore")
            links = extract_links(html, base, patterns)
            for url in links[:20]:
                content = fetch(url)
                name = re.sub(r"[^a-zA-Z0-9]+", "_", url)[:80]
                if url.lower().endswith(".pdf") or content[:4] == b"%PDF":
                    text = pdf_to_text(content)
                    save_raw(content, name + ".pdf")
                else:
                    save_raw(content, name + ".html")
                    text = html_to_text(content.decode("utf-8", errors="ignore"))
                chunks = chunk_text(text)
                write_passages(chunks, name)
        except Exception:
            continue


if __name__ == "__main__":
    run()


