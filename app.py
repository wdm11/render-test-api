from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"status": "root ok"}

@app.get("/ping")
def ping():
    return {"status": "ping ok"}

@app.get("/games")
def games(league: str):
    return {
        "games": [
            {"id": "game1", "away": "Oklahoma", "home": "Alabama"}
        ]
    }

import os
import requests

@app.get("/best-lines")
def best_lines(league: str, game_id: str):
    API_KEY = os.getenv("ODDS_API_KEY")

    sport_map = {
        "NFL": "americanfootball_nfl",
        "NCAAF": "americanfootball_ncaaf",
        "NCAAB": "basketball_ncaab",
        "NHL": "icehockey_nhl"
    }

    sport = sport_map[league]

    r = requests.get(
        f"https://api.the-odds-api.com/v4/sports/{sport}/odds",
        params={
            "apiKey": API_KEY,
            "regions": "us",
            "markets": "spreads,h2h,totals",
            "oddsFormat": "american"
        }
    )

    games = r.json()
    game = next(g for g in games if g["id"] == game_id)

    best = {
        "spread": None,
        "moneyline": None,
        "total": None
    }

    for book in game["bookmakers"]:
        for market in book["markets"]:
            for outcome in market["outcomes"]:
                if market["key"] == "spreads":
                    if not best["spread"] or outcome["point"] > best["spread"]["point"]:
                        best["spread"] = {
                            "team": outcome["name"],
                            "point": outcome["point"],
                            "price": outcome["price"],
                            "book": book["title"]
                        }

                if market["key"] == "h2h":
                    if not best["moneyline"] or outcome["price"] > best["moneyline"]["price"]:
                        best["moneyline"] = {
                            "team": outcome["name"],
                            "price": outcome["price"],
                            "book": book["title"]
                        }

                if market["key"] == "totals":
                    if not best["total"] or abs(outcome["point"]) > abs(best["total"]["point"]):
                        best["total"] = {
                            "line": f"{outcome['name']} {outcome['point']}",
                            "price": outcome["price"],
                            "book": book["title"]
                        }

    return best
