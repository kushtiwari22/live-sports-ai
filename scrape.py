from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as web
import trafilatura
from duckduckgo_search import DDGS


def http_get(url, timeout=15):
    r = web.get(url, impersonate="chrome", timeout=timeout)
    r.raise_for_status()
    return r


def search(query, n=6, days=None):
    limit = None
    if days is not None:
        if days <= 1:
            limit = "d"
        elif days <= 7:
            limit = "w"
        else:
            limit = "m"
    try:
        return list(DDGS().text(query, max_results=n, timelimit=limit))
    except Exception as e:
        print("search failed:", e)
        return []


def read_page(url):
    try:
        html = http_get(url).text
        text = trafilatura.extract(html) or ""
        meta = trafilatura.extract_metadata(html)
        date = meta.date if meta and meta.date else ""
        return {"url": url, "text": text, "date": date}
    except Exception:
        return {"url": url, "text": "", "date": ""}


def read_pages(urls):
    with ThreadPoolExecutor(max_workers=8) as pool:
        pages = list(pool.map(read_page, urls))
    return [p for p in pages if len(p["text"]) > 200]
