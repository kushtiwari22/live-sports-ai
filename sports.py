import datetime
import re
import time
from selectolax.parser import HTMLParser
import scrape

SPORTS = ["cricket", "football", "basketball", "tennis"]
ESPN = "https://site.api.espn.com/apis/site/v2/sports"

LEAGUES = {
    "football": [("soccer", x) for x in ["eng.1", "esp.1", "ger.1", "ita.1", "fra.1", "uefa.champions", "uefa.europa", "usa.1"]],
    "basketball": [("basketball", "nba"), ("basketball", "wnba")],
    "tennis": [("tennis", "atp"), ("tennis", "wta")],
}

cache = {}


def get(url, is_json=True, wait=8):
    if url in cache and time.time() - cache[url][0] < wait:
        return cache[url][1]
    r = scrape.http_get(url)
    data = r.json() if is_json else r.text
    cache[url] = (time.time(), data)
    return data


def name_of(c):
    thing = c.get("team") or c.get("athlete") or {}
    return thing.get("displayName", "?")


def read_competition(event, comp, sport, league):
    teams = comp.get("competitors", [])
    if len(teams) < 2:
        return None
    home = teams[0]
    away = teams[1]
    for t in teams:
        if t.get("homeAway") == "home":
            home = t
        else:
            away = t
    status = (comp.get("status") or event.get("status") or {}).get("type", {})
    if sport == "tennis":
        home_score = " ".join(str(int(x.get("value", 0))) for x in home.get("linescores", []))
        away_score = " ".join(str(int(x.get("value", 0))) for x in away.get("linescores", []))
    else:
        home_score = str(home.get("score", ""))
        away_score = str(away.get("score", ""))
    return {
        "id": league + ":" + str(comp.get("id") or event.get("id")),
        "sport": sport,
        "league": league,
        "home": name_of(home),
        "away": name_of(away),
        "home_score": home_score,
        "away_score": away_score,
        "state": status.get("state", "pre"),
        "detail": status.get("shortDetail", ""),
        "date": (comp.get("date") or event.get("date") or "")[:10],
    }


def page_lines(html):
    tree = HTMLParser(html)
    tree.strip_tags(["script", "style", "nav", "footer"])
    text = tree.body.text(separator="\n") if tree.body else ""
    return [l.strip() for l in text.split("\n") if len(l.strip()) > 2]


def list_matches(sport):
    matches = []
    if sport == "cricket":
        html = get("https://www.cricbuzz.com/cricket-match/live-scores", is_json=False, wait=30)
        found = re.findall(r'href="/live-cricket-scores/(\d+)/([a-z0-9\-]+)"', html)
        done = set()
        for match_id, slug in found:
            if match_id in done:
                continue
            done.add(match_id)
            title = slug.replace("-", " ")
            parts = title.split(" vs ")
            matches.append({
                "id": "cb:" + match_id, "sport": "cricket", "league": "cricket",
                "home": parts[0].upper(), "away": parts[-1].upper() if len(parts) > 1 else "",
                "home_score": "", "away_score": "", "state": "in", "detail": title,
                "date": str(datetime.date.today()),
            })
        return matches
    for espn_sport, league in LEAGUES[sport]:
        try:
            data = get(ESPN + "/" + espn_sport + "/" + league + "/scoreboard", wait=15)
        except Exception:
            continue
        for event in data.get("events", []):
            comps = list(event.get("competitions", []))
            for g in event.get("groupings", []):
                comps = comps + g.get("competitions", [])
            for comp in comps:
                m = read_competition(event, comp, sport, league)
                if m:
                    matches.append(m)
    order = {"in": 0, "pre": 1, "post": 2}
    matches.sort(key=lambda m: order.get(m["state"], 3))
    return matches


def team_stats_text(data):
    lines = []
    for team in data.get("boxscore", {}).get("teams", []):
        stats = [s.get("label", "") + ": " + str(s.get("displayValue", "")) for s in team.get("statistics", [])[:14]]
        lines.append(team.get("team", {}).get("displayName", "") + " -> " + ", ".join(stats))
    return "\n".join(lines)


def get_match_details(sport, match_id):
    if sport == "cricket":
        html = get("https://www.cricbuzz.com/live-cricket-scores/" + match_id.split(":")[1], is_json=False, wait=6)
        lines = page_lines(html)
        match = {"id": match_id, "sport": sport, "league": "cricket", "home": "", "away": "",
                 "home_score": "", "away_score": "", "state": "in", "detail": "",
                 "date": str(datetime.date.today())}
        for m in list_matches("cricket"):
            if m["id"] == match_id:
                match = m
        for l in lines:
            if re.search(r"\d+[/-]\d+", l) and len(l) < 60:
                match["detail"] = l
                break
        words = ["run", "four", "six", "out", "wicket", "bowled", "caught", "lbw", "wide"]
        events = []
        for l in lines:
            if len(l) > 40 and any(w in l.lower() for w in words):
                events.append({"id": str(abs(hash(l))), "clock": "", "text": l})
        return match, events, "\n".join(lines[:50])[:2500]

    league, event_id = match_id.split(":", 1)
    espn_sport = [s for s, l in LEAGUES[sport] if l == league][0]
    data = get(ESPN + "/" + espn_sport + "/" + league + "/summary?event=" + event_id, wait=6)
    comp = (data.get("header", {}).get("competitions") or [{}])[0]
    match = read_competition({"id": event_id}, comp, sport, league)
    if match is None:
        match = {"id": match_id, "sport": sport, "league": league, "home": "", "away": "",
                 "home_score": "", "away_score": "", "state": "pre", "detail": "", "date": ""}
    match["id"] = match_id

    events = []
    raw = []
    if sport == "football":
        raw = data.get("commentary", [])
    if sport == "basketball":
        raw = data.get("plays", [])
    for x in raw:
        text = x.get("text") or x.get("shortText")
        if not text:
            continue
        clock = (x.get("time") or x.get("clock") or {}).get("displayValue", "")
        if sport == "basketball":
            text = text + " (" + str(x.get("awayScore", "")) + "-" + str(x.get("homeScore", "")) + ")"
        events.append({"id": str(x.get("sequence") or x.get("id")), "clock": clock, "text": text})
    return match, events, team_stats_text(data)


def get_players(sport, match_id):
    match = None
    if sport == "tennis":
        match, events, stats = get_match_details(sport, match_id)
        return [{"name": match["home"], "team": match["home"]}, {"name": match["away"], "team": match["away"]}]
    if sport == "cricket":
        return []
    league, event_id = match_id.split(":", 1)
    espn_sport = [s for s, l in LEAGUES[sport] if l == league][0]
    data = get(ESPN + "/" + espn_sport + "/" + league + "/summary?event=" + event_id, wait=60)
    players = []
    if sport == "football":
        for team in data.get("rosters", []):
            team_name = team.get("team", {}).get("displayName", "")
            ordered = sorted(team.get("roster", []), key=lambda p: not p.get("starter", False))
            for p in ordered[:11]:
                players.append({"name": p.get("athlete", {}).get("displayName", ""), "team": team_name})
    if sport == "basketball":
        for team in data.get("boxscore", {}).get("players", []):
            team_name = team.get("team", {}).get("displayName", "")
            for group in team.get("statistics", [])[:1]:
                for p in group.get("athletes", [])[:8]:
                    players.append({"name": p.get("athlete", {}).get("displayName", ""), "team": team_name})
    return [p for p in players if p["name"]]
