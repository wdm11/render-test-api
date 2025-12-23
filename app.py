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

ALLOWED_BOOKS = {
    "DraftKings": {
        "key": "draftkings",
        "deeplink": "draftkings://sportsbook"
    },
    "FanDuel": {
        "key": "fanduel",
        "deeplink": "fanduel://sportsbook"
    },
    "BetMGM": {
        "key": "betmgm",
        "deeplink": "betmgm://sports"
    },
    "Caesars": {
        "key": "caesars",
        "deeplink": "caesars://sportsbook"
    }
}

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
    best = {
        "spread": {},
        "moneyline": {},
        "total": {
            "over": None,
            "under": None
        }
    }

    # Iterate safely through bookmakers and markets
    for book in game.get("bookmakers", []):
        book_title = book.get("title")

        if book_title not in ALLOWED_BOOKS:
            continue

        for market in book.get("markets", []):
            key = market.get("key")
            outcomes = market.get("outcomes", [])

            # -------- SPREADS --------
            if key == "spreads":
                for outcome in outcomes:
                    team = outcome.get("name")
                    point = outcome.get("point")
                    price = outcome.get("price")

                    if team not in best["spread"] or abs(point) < abs(best["spread"][team]["point"]):
                        best["spread"][team] = {
                            "point": point,
                            "price": price,
                            "book": book_title,
                            "deeplink": ALLOWED_BOOKS[book_title]["deeplink"]
                        }

            # -------- MONEYLINES --------
            elif key == "h2h":
                for outcome in outcomes:
                    team = outcome.get("name")
                    price = outcome.get("price")

                    if team not in best["moneyline"] or price > best["moneyline"][team]["price"]:
                        best["moneyline"][team] = {
                            "price": price,
                            "book": book_title,
                            "deeplink": ALLOWED_BOOKS[book_title]["deeplink"]
                        }

            # -------- TOTALS --------
            elif key == "totals":
                for outcome in outcomes:
                    side = outcome.get("name")  # Over / Under
                    point = outcome.get("point")
                    price = outcome.get("price")

                    if side == "Over":
                        if not best["total"]["over"] or point < best["total"]["over"]["point"]:
                            best["total"]["over"] = {
                                "point": point,
                                "price": price,
                                "book": book_title,
                                "deeplink": ALLOWED_BOOKS[book_title]["deeplink"]
                            }
                    elif side == "Under":
                        if not best["total"]["under"] or point > best["total"]["under"]["point"]:
                            best["total"]["under"] = {
                                "point": point,
                                "price": price,
                                "book": book_title,
                                "deeplink": ALLOWED_BOOKS[book_title]["deeplink"]
                            }

    # -------- ADD TEAMS --------
    teams = {
        "home": game.get("home_team"),
        "away": game.get("away_team")
    }

    # -------- RETURN RESPONSE --------
    return {
        "game_id": game_id,
        "league": league,
        "teams": teams,
        "best_lines": best
    }