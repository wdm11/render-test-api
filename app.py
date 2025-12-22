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
    # Normalize league input
    league = league.strip().upper()
    sport = SPORT_MAP.get(league)
    if not sport:
        return {"error": f"Invalid league '{league}'", "valid_leagues": list(SPORT_MAP.keys())}

    # Fetch odds data from Odds API
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "spreads,h2h,totals",
        "eventIds": game_id
    }
    resp = requests.get(url, params=params)
    data = resp.json()

    if not data:
        return {"error": "No data returned from Odds API"}

    game = data[0]  # Only one game for eventId

    best_lines = {
        "spread": {},
        "moneyline": {},
        "total": {}
    }

    # Loop through bookmakers
    for book in game.get("bookmakers", []):
        for market in book.get("markets", []):
            key = market.get("key")
            outcomes = market.get("outcomes", [])

            if key == "spreads":
                for outcome in outcomes:
                    team = outcome["name"]
                    point = outcome["point"]
                    # Pick the most favorable spread (closest to 0 for betting)
                    if team not in best_lines["spread"] or abs(point) < abs(best_lines["spread"][team]["point"]):
                        best_lines["spread"][team] = {"point": point, "book": book["title"]}

            elif key == "h2h":
                for outcome in outcomes:
                    team = outcome["name"]
                    price = outcome["price"]
                    # Pick the highest payout for the team
                    if team not in best_lines["moneyline"] or price > best_lines["moneyline"][team]["price"]:
                        best_lines["moneyline"][team] = {"price": price, "book": book["title"]}

            elif key == "totals":
                for outcome in outcomes:
                    side = outcome["name"]  # "Over" or "Under"
                    line = outcome["point"]

                    # Over: lowest line (easier to hit)
                    if side == "Over":
                        if "Over" not in best_lines["total"] or line < best_lines["total"]["Over"]["line"]:
                            best_lines["total"]["Over"] = {"line": line, "book": book["title"]}

                    # Under: highest line (safer payout)
                    elif side == "Under":
                        if "Under" not in best_lines["total"] or line > best_lines["total"]["Under"]["line"]:
                            best_lines["total"]["Under"] = {"line": line, "book": book["title"]}

    return {"best_lines": best_lines}
