from fastapi import FastAPI
import os
import requests

app = FastAPI()

@app.get("/ping")
def ping():
    return {"status": "ok"}


LEAGUES = {
    "NFL": "americanfootball_nfl",
    "NCAAF": "americanfootball_ncaaf",
    "NCAAB": "basketball_ncaab",
    "NHL": "icehockey_nhl"
}

@app.get("/games")
def get_games(league: str):
    return {
        "games": [
            {"id": "test1", "away": "Oklahoma", "home": "Alabama"},
            {"id": "test2", "away": "Texas", "home": "Georgia"}
        ]
    }
