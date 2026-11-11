import datetime
import difflib
import rag
import scrape
import sports
from llm import ask_llm, ask_llm_json


def understand(question, history):
    system = ("You analyse sports questions. Return JSON with keys: "
              "'type' (one of: live, history, general), "
              "'teams' (list of team or player names mentioned, full official names), "
              "'search_query' (a short, standalone web search query). "
              "Use the chat history to resolve words like 'he' or 'they'.")
    return ask_llm_json(system, "History:\n" + history + "\n\nQuestion: " + question)


def match_text(sport, match_id, count):
    match, events, stats = sports.get_match_details(sport, match_id)
    recent = "\n".join(e["clock"] + " " + e["text"] for e in events[-count:])
    return (match["home"] + " " + match["home_score"] + " - " + match["away_score"] + " " + match["away"] +
            " (" + match["detail"] + ", state=" + match["state"] + ")\n" + stats + "\n" + recent + "\n\n")


def get_live_text(teams):
    found = ""
    count = 0
    for sport in sports.SPORTS:
        for m in sports.list_matches(sport):
            for team in teams:
                names = [m["home"].lower(), m["away"].lower()]
                close = difflib.get_close_matches(team.lower(), names, n=1, cutoff=0.6)
                if close and count < 3:
                    count += 1
                    found += match_text(sport, m["id"], 8)
    return found


def web_search_and_store(query, days):
    results = scrape.search(query, n=6, days=days)
    for r in results:
        rag.add_text(r["title"] + ". " + r["body"], r["href"])
    for page in scrape.read_pages([r["href"] for r in results[:5]]):
        rag.add_text(page["text"][:8000], page["url"])
    return len(results)


def grade_chunks(question, found):
    if not found:
        return []
    listing = ""
    for i, c in enumerate(found):
        listing += str(i + 1) + ". " + c["text"][:400] + "\n"
    result = ask_llm_json("Pick the text pieces that help answer the question. "
                          "Return JSON like {\"relevant\": [1, 3]}.",
                          "Question: " + question + "\n\n" + listing)
    numbers = result.get("relevant", [])
    good = [found[n - 1] for n in numbers if isinstance(n, int) and 0 < n <= len(found)]
    return good if good else found[:2]


def is_grounded(answer, context):
    result = ask_llm_json("Check if the answer is supported by the context. "
                          "Return JSON like {\"grounded\": true}.",
                          "Context:\n" + context + "\n\nAnswer:\n" + answer)
    return result.get("grounded", True)


def answer_question(question, history_list, days=7, sport=None, match_id=None):
    steps = []
    history = "\n".join(history_list[-6:])

    plan = understand(question, history)
    qtype = plan.get("type", "general")
    teams = plan.get("teams", [])
    query = plan.get("search_query") or question
    steps.append("1. Understood: type=" + str(qtype) + ", teams=" + str(teams) + ", query='" + query + "'")

    live_text = ""
    if sport and match_id:
        live_text = match_text(sport, match_id, 15)
    elif qtype == "live" and teams:
        live_text = get_live_text(teams)
    steps.append("2. Live data: " + ("found" if live_text else "none"))

    answer = ""
    sources = []
    for attempt in range(2):
        if qtype != "general":
            n = web_search_and_store(query, days)
            steps.append("3. Web search (try " + str(attempt + 1) + "): " + str(n) + " results stored")
        found = rag.search(query, k=6)
        steps.append("4. Vector search: " + str(len(found)) + " chunks")
        good = grade_chunks(question, found)
        steps.append("5. Grader kept " + str(len(good)) + " chunks")

        context = "LIVE DATA:\n" + live_text + "\n\nDOCUMENTS:\n" + "\n---\n".join(c["text"] for c in good)
        system = ("You are a sports analyst. Today is " + str(datetime.date.today()) + ". "
                  "Answer using the context. Live data is the most reliable. "
                  "If the context does not contain the answer, say you could not find it. Never invent scores.")
        answer = ask_llm(system, "History:\n" + history + "\n\nContext:\n" + context + "\n\nQuestion: " + question,
                         temperature=0.3)
        sources = list(set(c["source"] for c in good))
        steps.append("6. Answer generated")

        if is_grounded(answer, context):
            steps.append("7. Check passed")
            break
        steps.append("7. Check failed, rewriting the query")
        query = ask_llm("Rewrite this as a better, shorter web search query. Reply with the query only.", query, temperature=0.7)
    return {"answer": answer, "sources": sources, "steps": steps}
