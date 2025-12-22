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

@app.get("/debug-league")
def debug_league(league: str):
    return {
        "raw": league,
        "len": len(league),
        "chars": [c for c in league]
    }
    
@app.get("/")
def root():
    return {"status": "root ok"}

@app.get("/ping")
def ping():
    return {"status": "ping ok"}

@app.get("/games")
def get_games(league: str):
    # Normalize league input
    league = league.strip().upper()
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
    # Fetch data from Odds API
    url = f"https://api.the-odds-api.com/v4/sports/{league}/odds?apiKey=YOUR_KEY&regions=us&markets=spreads,h2h,totals&eventIds={game_id}"
    resp = requests.get(url)
    data = resp.json()
    game = data[0]  # Assuming 1 game per id

    best_lines = {
        "spread": {},
        "moneyline": {},
        "total": {}
    }

    # Loop through bookmakers
    for book in game["bookmakers"]:
        for market in book["markets"]:
            if market["key"] == "spreads":
                for outcome in market["outcomes"]:
                    team = outcome["name"]
                    point = outcome["point"]
                    # Update best spread
                    if team not in best_lines["spread"] or abs(point) < abs(best_lines["spread"][team]["point"]):
                        best_lines["spread"][team] = {"point": point, "book": book["title"]}

            elif market["key"] == "h2h":
                for outcome in market["outcomes"]:
                    team = outcome["name"]
                    price = outcome["price"]
                    if team not in best_lines["moneyline"] or price > best_lines["moneyline"][team]["price"]:
                        best_lines["moneyline"][team] = {"price": price, "book": book["title"]}

            elif market["key"] == "totals":
                for outcome in market["outcomes"]:
                    side = outcome["name"]  # "Over" or "Under"
                    line = outcome["point"]
                    # Over: choose lowest
                    if side == "Over":
                        if "Over" not in best_lines["total"] or line < best_lines["total"]["Over"]["line"]:
                            best_lines["total"]["Over"] = {"line": line, "book": book["title"]}
                    # Under: choose highest
                    if side == "Under":
                        if "Under" not in best_lines["total"] or line > best_lines["total"]["Under"]["line"]:
                            best_lines["total"]["Under"] = {"line": line, "book": book["title"]}

    return {"best_lines": best_lines}
