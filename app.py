from fastapi import FastAPI
import os
import requests

app = FastAPI()

API_KEY = os.getenv("ODDS_API_KEY")

SPORT_MAP = {
    "NFL": "americanfootball_nfl",
    "NCAAF": "americanfootball_ncaaf",
    "NCAAB": "basketball_ncaab",
    "NHL": "icehockey_nhl"
}

BASE_URL = "https://api.the-odds-api.com/v4/sports"

@app.get("/")
def root():
    return {"status": "root ok"}

@app.get("/ping")
def ping():
    return {"status": "ping ok"}

@app.get("/games")
def get_games(league: str):
    # Normalize league input
    league = league.upper()
    if league not in SPORT_MAP:
        return {"error": f"Invalid league '{league}'. Valid leagues: {list(SPORT_MAP.keys())}"}

    sport = SPORT_MAP[league]

    # Call Odds API
    try:
        r = requests.get(
            f"{BASE_URL}/{sport}/odds",
            params={
                "apiKey": API_KEY,
                "regions": "us",
                "markets": "h2h,spreads,totals",
                "oddsFormat": "american"
            },
            timeout=10
        )
        r.raise_for_status()
    except requests.RequestException as e:
        return {"error": "Failed to fetch odds from API", "details": str(e)}

    games = r.json()
    if not games:
        return {"error": "No games returned from Odds API for this league"}

    # Build simple list for Shortcut
    game_list = []
    for g in games:
        game_list.append({
            "id": g.get("id"),
            "away": g.get("away_team"),
            "home": g.get("home_team")
        })

    return {"games": game_list}


@app.get("/best-lines")
def best_lines(league: str, game_id: str):
    # Normalize league input
    league = league.upper()
    if league not in SPORT_MAP:
        return {"error": f"Invalid league '{league}'. Valid leagues: {list(SPORT_MAP.keys())}"}

    sport = SPORT_MAP[league]

    # Call Odds API
    try:
        r = requests.get(
            f"{BASE_URL}/{sport}/odds",
            params={
                "apiKey": API_KEY,
                "regions": "us",
                "markets": "spreads,h2h,totals",
                "oddsFormat": "american"
            },
            timeout=10
        )
        r.raise_for_status()
    except requests.RequestException as e:
        return {"error": "Failed to fetch odds from API", "details": str(e)}

    games = r.json()
    if not games:
        return {"error": "No games returned from Odds API for this league"}

    # Find the requested game
    game = next((g for g in games if g.get("id") == game_id), None)
    if not game:
        return {"error": f"Game ID '{game_id}' not found in Odds API response"}

    # Initialize best lines container
    best = {"spread": None, "moneyline": None, "total": None}

    # Iterate safely through bookmakers and markets
    for book in game.get("bookmakers", []):
        book_title = book.get("title")
        for market in book.get("markets", []):
            key = market.get("key")
            outcomes = market.get("outcomes", [])

            if key == "spreads":
                for outcome in outcomes:
                    # Pick the first spread (or enhance logic later)
                    if not best["spread"]:
                        best["spread"] = {
                            "team": outcome.get("name"),
                            "point": outcome.get("point"),
                            "price": outcome.get("price"),
                            "book": book_title
                        }

            if key == "h2h":
                for outcome in outcomes:
                    if not best["moneyline"]:
                        best["moneyline"] = {
                            "team": outcome.get("name"),
                            "price": outcome.get("price"),
                            "book": book_title
                        }

            if key == "totals":
                for outcome in outcomes:
                    if not best["total"]:
                        best["total"] = {
                            "line": f"{outcome.get('name')} {outcome.get('point')}",
                            "price": outcome.get("price"),
                            "book": book_title
                        }

    return {"game_id": game_id, "league": league, "best_lines": best}
