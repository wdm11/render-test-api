import os
import requests
from fastapi import FastAPI

app = FastAPI()

API_KEY = os.getenv("ODDS_API_KEY")

LEAGUES = {
    "NFL": "americanfootball_nfl",
    "NCAAF": "americanfootball_ncaaf",
    "NCAAB": "basketball_ncaab",
    "NHL": "icehockey_nhl"
}

BASE_URL = "https://api.the-odds-api.com/v4/sports"


@app.get("/games")
def get_games(league: str):
    sport = LEAGUES.get(league)
    r = requests.get(
        f"{BASE_URL}/{sport}/odds",
        params={
            "apiKey": API_KEY,
            "regions": "us",
            "markets": "h2h,spreads,totals"
        }
    )

    games = []
    for g in r.json():
        games.append({
            "id": g["id"],
            "away": g["away_team"],
            "home": g["home_team"]
        })

    return {"games": games}
