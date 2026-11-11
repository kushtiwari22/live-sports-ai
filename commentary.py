import random
import threading
import time
import match_facts
import rag
import sports
from llm import ask_llm

POLL_SECONDS = 10
rooms = {}

STYLE = {
    "cricket": "an elite cricket commentator. Talk about the shot, line and length, fielders, run rate and partnerships.",
    "football": "an energetic football commentator. Talk about build-up play, tactics, momentum, cards and chances.",
    "basketball": "a lively basketball commentator. Talk about scoring runs, matchups, shooting and momentum.",
    "tennis": "a sharp tennis commentator. Talk about the game flow, break points and momentum.",
}


def get_feed(sport, match_id, since=0):
    key = sport + "|" + match_id
    if key not in rooms:
        rooms[key] = {"match": {}, "feed": [], "seen": set(), "stats": "", "last_viewed": time.time(),
                      "done_states": [], "facts": [], "next_fact_time": time.time() + 120,
                      "milestones": 0, "milestone_done": set()}
        threading.Thread(target=watch, args=(sport, match_id, key), daemon=True).start()
        threading.Thread(target=load_facts, args=(rooms[key], sport, match_id), daemon=True).start()
    room = rooms[key]
    room["last_viewed"] = time.time()
    return {"match": room["match"], "feed": room["feed"][since:], "total": len(room["feed"])}


def watch(sport, match_id, key):
    room = rooms[key]
    while time.time() - room["last_viewed"] < 300:
        try:
            update(room, sport, match_id)
            drip_fact(room)
        except Exception as e:
            print("watch error:", e)
        time.sleep(POLL_SECONDS)
    del rooms[key]


def update(room, sport, match_id):
    match, events, stats = sports.get_match_details(sport, match_id)
    room["match"] = match
    room["stats"] = stats
    new_events = [e for e in events if e["id"] not in room["seen"]]

    if len(room["seen"]) == 0 and len(new_events) > 15:
        old = new_events[:-15]
        new_events = new_events[-15:]
        for e in old:
            room["seen"].add(e["id"])
        old_text = "\n".join(e["clock"] + " " + e["text"] for e in old[-60:])
        summary = narrate(room, sport, "Summarise the match so far in 4 to 6 sentences:\n" + old_text)
        add_item(room, "story so far", "", summary)

    if len(events) == 0 and match.get("state") == "in":
        score = match["home"] + " " + match["home_score"] + " - " + match["away_score"] + " " + match["away"]
        if score not in room["seen"]:
            new_events = [{"id": score, "clock": "", "text": score}]

    for i in range(0, len(new_events), 10):
        batch = new_events[i:i + 10]
        numbered = ""
        for n, e in enumerate(batch):
            numbered += str(n + 1) + ". [" + e["clock"] + "] " + e["text"] + "\n"
        reply = narrate(room, sport, "Write 1-3 sentences of live commentary for each numbered event. "
                                     "Reply as '1. text' per line.\n" + numbered)
        lines = {}
        for line in reply.split("\n"):
            if line[:1].isdigit() and ". " in line:
                number, text = line.split(". ", 1)
                if number.isdigit():
                    lines[int(number)] = text
        for n, e in enumerate(batch):
            room["seen"].add(e["id"])
            add_item(room, "event", e["clock"], lines.get(n + 1, e["text"]))
        check_milestones(room, sport, match, batch)

    state = match.get("state")
    if len(new_events) == 0 and state in ("pre", "post") and state not in room["done_states"]:
        room["done_states"].append(state)
        if state == "pre":
            text = narrate(room, sport, "Write a 5-7 sentence match preview.")
        else:
            text = narrate(room, sport, "Write a 5-7 sentence match recap with key moments.")
        add_item(room, state, "", text)


def check_milestones(room, sport, match, batch):
    checked = 0
    for e in batch:
        if checked >= 2 or room["milestones"] >= 8:
            break
        if not match_facts.is_milestone(sport, e["text"]):
            continue
        checked += 1
        found = match_facts.milestone_fact(sport, e["text"], match, room["stats"])
        if found:
            name, kind = found[0].split("|")
            last_name = name.split()[-1].lower()
            key = last_name + "|" + kind
            if key not in room["milestone_done"]:
                room["milestone_done"].add(key)
                room["milestones"] += 1
                room["facts"] = [f for f in room["facts"] if last_name not in f.lower()]
                add_item(room, "milestone", e["clock"], found[1])


def narrate(room, sport, task):
    m = room["match"]
    info = (m.get("home", "") + " " + m.get("home_score", "") + " - " + m.get("away_score", "") + " " +
            m.get("away", "") + " (" + m.get("detail", "") + ")")
    recent = "\n".join(i["text"] for i in room["feed"][-5:])
    system = ("You are " + STYLE[sport] + " Use ONLY the facts given. Never invent scores, names or stats. "
              "Use the match stats in your commentary.")
    user = "MATCH: " + info + "\nSTATS:\n" + room["stats"] + "\nLATEST COMMENTARY:\n" + recent + "\n\nTASK: " + task
    try:
        return ask_llm(system, user, max_tokens=600)
    except Exception as e:
        return "(commentary unavailable: " + str(e)[:80] + ")"


def add_item(room, kind, clock, text):
    room["feed"].append({"kind": kind, "clock": clock, "text": text})
    m = room["match"]
    source = m.get("home", "") + " vs " + m.get("away", "") + " commentary"
    rag.add_text(source + " " + clock + ": " + text, source)


def load_facts(room, sport, match_id):
    for i in range(30):
        if room["match"]:
            break
        time.sleep(1)
    try:
        room["facts"] = match_facts.build_fact_pack(sport, match_id, room["match"], room["stats"])
        print("fact pack ready:", len(room["facts"]), "facts")
    except Exception as e:
        print("fact pack failed:", e)


def drip_fact(room):
    if room["match"].get("state") == "post":
        return
    if len(room["facts"]) > 0 and time.time() >= room["next_fact_time"]:
        add_item(room, "insight", "", room["facts"].pop(0))
        room["next_fact_time"] = time.time() + random.randint(120, 300)
