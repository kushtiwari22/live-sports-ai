from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import commentary
import qa
import sports

app = FastAPI()


class Question(BaseModel):
    question: str
    history: list[str] = []
    days: int = 7
    sport: str | None = None
    match_id: str | None = None


@app.get("/")
def home():
    return FileResponse("index.html")


@app.get("/api/matches")
def matches(sport: str):
    if sport not in sports.SPORTS:
        raise HTTPException(400, "unknown sport")
    return sports.list_matches(sport)


@app.get("/api/commentary")
def get_commentary(sport: str, match_id: str, since: int = 0):
    return commentary.get_feed(sport, match_id, since)


@app.post("/api/ask")
def ask(body: Question):
    try:
        return qa.answer_question(body.question, body.history, body.days, body.sport, body.match_id)
    except Exception as e:
        raise HTTPException(500, str(e))
