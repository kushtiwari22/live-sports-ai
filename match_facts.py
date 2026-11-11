import json
import os
import time
import player_stats
import rag
import scrape
import sports
from llm import ask_llm, ask_llm_json

TRIGGERS = {
    "football": ["goal!", "own goal", "red card"],
    "cricket": ["century", "hundred", "fifty", "hat-trick", "three wickets", "3 wickets",
                "four wickets", "five wickets", "five-wicket", "3-wicket"],
    "basketball": ["triple-double", "career high", "career-high"],
    "tennis": ["match point", "set point"],
}

NEXT_COUNT = {
    "fifty": "fifties",
    "hundred": "hundreds",
    "three_wickets": "three_wicket_hauls",
    "four_wickets": "four_wicket_hauls",
    "five_wickets": "five_wicket_hauls",
}


def snippets(query, n=3):
    text = ""
    for r in scrape.search(query, n=n):
        text += "- " + r["title"] + ": " + r["body"] + "\n"
    return text


def build_fact_pack(sport, match_id, match, stats):
    cache_file = "data/facts_" + match_id.replace(":", "_") + ".json"
    if os.path.exists(cache_file) and time.time() - os.path.getmtime(cache_file) < 6 * 3600:
        return json.load(open(cache_file, encoding="utf-8"))

    home, away = match["home"], match["away"]
    players = sports.get_players(sport, match_id)
    if sport == "cricket" and not players:
        found = ask_llm_json("List the main players (max 8) in this cricket match text. "
                             "Return JSON like {\"players\": [\"name\"]}.", stats[:2000])
        players = [{"name": n, "team": ""} for n in found.get("players", [])]

    queries = [home + " vs " + away + " head to head record history",
               home + " recent form this season",
               away + " recent form this season"]
    for p in players[:8]:
        queries.append(p["name"] + " career stats records milestones")

    notes = ""
    for q in queries:
        notes += "SEARCH: " + q + "\n" + snippets(q) + "\n"

    system = ("You are a sports researcher. From the search notes ONLY, write interesting facts for a live "
              "commentary box. Each fact is 1-2 sentences, names the player or team, and contains a real "
              "number or record from the notes. Never use anything that is not in the notes. "
              "Return JSON like {\"facts\": [\"...\"]} with up to 15 facts.")
    result = ask_llm_json(system, "Match: " + home + " vs " + away + "\nStats:\n" + stats[:800] +
                          "\n\nNOTES:\n" + notes[:7000])
    facts = [f for f in result.get("facts", []) if isinstance(f, str)]
    json.dump(facts, open(cache_file, "w", encoding="utf-8"))
    for f in facts:
        rag.add_text(home + " vs " + away + " fact: " + f, home + " vs " + away + " facts")
    return facts


def is_milestone(sport, event_text):
    text = event_text.lower()
    for word in TRIGGERS.get(sport, []):
        if word in text:
            return True
    return False


def milestone_fact(sport, event_text, match, match_text):
    system = ("Find the player and the milestone in this event. Return JSON like "
              "{\"player\": \"full name\", \"milestone\": \"fifty|hundred|three_wickets|four_wickets|"
              "five_wickets|goal|other\", \"this_match\": \"the player's figures in this match, "
              "copied from the text only\"}. If you are not sure, return {}.")
    who = ask_llm_json(system, "Event: " + event_text + "\n\nMatch text:\n" + match_text[:1500])
    player = who.get("player")
    if not player:
        return None

    sources = player_stats.get_sources(player, sport, match)
    if sources == "":
        return None

    counts_up = NEXT_COUNT.get(who.get("milestone", ""), "")
    system = ("You are a sports statistician writing for a live commentary box. You get several web pages "
              "with career stats of one player. They were written at different times: some are older, "
              "some may already include part of today's match. You also get the live figures from the "
              "match page. Compare all of them, use the page dates, and work out the best estimate of "
              "the player's career totals BEFORE this match and AFTER this milestone. "
              "Example: if a page says 313 runs and the live page shows he has 50 in this match, "
              "decide whether the page already includes those runs. "
              "You do not need to be perfectly sure. When sources disagree, pick the most likely numbers "
              "and say 'around' or 'roughly'. "
              "Write 2-3 sentences: the player, the milestone, his career totals (runs, fifties, hundreds, "
              "wickets, 3/4/5-wicket hauls, goals, whatever is relevant) and any record. "
              "Use only numbers that appear in the sources or the match text. "
              "If there is nothing useful at all, reply exactly: NONE")
    user = ("Player: " + player + "\nMilestone: " + str(who.get("milestone")) +
            ("\nThis milestone adds 1 to his " + counts_up + " count." if counts_up else "") +
            "\nThis match: " + str(who.get("this_match")) +
            "\nMatch " + match["home"] + " vs " + match["away"] + " on " + str(match.get("date")) +
            "\n\nLIVE MATCH PAGE:\n" + match_text[:2000] +
            "\n\nWEB SOURCES:\n" + sources)
    text = ask_llm(system, user, temperature=0.2, max_tokens=250)
    if text.strip().upper().startswith("NONE"):
        return None
    return player + "|" + str(who.get("milestone")), text
