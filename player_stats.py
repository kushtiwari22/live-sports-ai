import scrape

saved = {}


def find_urls(player, sport):
    urls = []
    for q in (player + " career statistics " + sport, player + " " + sport + " stats profile records"):
        for r in scrape.search(q, n=5):
            if r["href"] not in urls:
                urls.append(r["href"])
    return urls[:6]


def cut_text(text):
    i = text.lower().find("career")
    start = max(0, i - 200) if i >= 0 else 0
    return text[start:start + 1500]


def get_sources(player, sport, match):
    key = player + "|" + match["id"]
    if key in saved:
        return saved[key]
    pages = scrape.read_pages(find_urls(player, sport))
    listing = ""
    for n, p in enumerate(pages):
        listing += ("SOURCE " + str(n + 1) + " (" + p["url"] + ") page date: " +
                    str(p["date"] or "unknown") + "\n" + cut_text(p["text"]) + "\n\n")
    saved[key] = listing
    return listing
