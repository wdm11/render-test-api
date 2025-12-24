from fastapi import FastAPI
import os
import requests
from statistics import mean

app = FastAPI()

API_KEY = os.getenv("ODDS_API_KEY")

SPORT_MAP = {
    "NFL": "americanfootball_nfl",
    "NCAAF": "americanfootball_ncaaf",
    "NCAAB": "basketball_ncaab",
    "NBA": "basketball_nba",
    "MLB": "baseball_mlb",
    "NHL": "icehockey_nhl",
    "MLS": "soccer_usa_mls",
    "EPL": "soccer_epl",
    "UFC": "mma_mixed_martial_arts"
}

BASE_URL = "https://api.the-odds-api.com/v4/sports"

ALLOWED_BOOKS = {
    "DraftKings": {
        "key": "draftkings",
        "deeplink": "https://sportsbook.draftkings.com"
    },
    "FanDuel": {
        "key": "fanduel",
        "deeplink": "https://sportsbook.fanduel.com"
    },
    "BetMGM": {
        "key": "betmgm",
        "deeplink": "https://sports.betmgm.com"
    },
    "Caesars": {
        "key": "caesars",
        "deeplink": "https://www.caesars.com/sportsbook"
    },
    "bet365": {
        "key": "bet365",
        "deeplink": "https://www.bet365.com"
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
    league = league.upper()
    if league not in SPORT_MAP:
        return {"error": f"Invalid league '{league}'"}

    sport = SPORT_MAP[league]

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
        return {"error": "Odds API error", "details": str(e)}

    games = r.json()
    game = next((g for g in games if g.get("id") == game_id), None)
    if not game:
        return {"error": "Game not found"}

    best = {
        "spread": {},
        "moneyline": {},
        "total": {"over": None, "under": None}
    }

    consensus = {
        "spread": {},
        "moneyline": {},
        "total": {"over": [], "under": []}
    }

    for book in game.get("bookmakers", []):
        book_title = book.get("title")
        if book_title not in ALLOWED_BOOKS:
            continue

        for market in book.get("markets", []):
            key = market.get("key")

            for outcome in market.get("outcomes", []):
                team = outcome.get("name")
                point = outcome.get("point")
                price = outcome.get("price")

                # -------- SPREADS (directionally correct) --------
if key == "spreads":
    for outcome in outcomes:
        team = outcome.get("name")
        point = outcome.get("point")
        price = outcome.get("price")

        current = best["spread"].get(team)

        if not current:
            take = True
        elif point > 0 and point > current["point"]:
            # Underdog → higher number is better
            take = True
        elif point < 0 and point > current["point"]:
            # Favorite → closer to zero (less negative) is better
            take = True
        elif point == current["point"] and price > current["price"]:
            # Same number → better price
            take = True
        else:
            take = False

        if take:
            best["spread"][team] = {
                "point": point,
                "price": price,
                "book": book_title,
                "deeplink": ALLOWED_BOOKS[book_title]["deeplink"]
            }

        # Always collect for consensus
        consensus["spread"].setdefault(team, []).append(point)

                elif key == "h2h":
                    consensus["moneyline"].setdefault(team, []).append(price)

                    if team not in best["moneyline"] or price > best["moneyline"][team]["price"]:
                        best["moneyline"][team] = {
                            "price": price,
                            "book": book_title,
                            "deeplink": ALLOWED_BOOKS[book_title]["deeplink"]
                        }

                elif key == "totals":
                    if team == "Over":
                        consensus["total"]["over"].append(point)

                        if not best["total"]["over"] or point < best["total"]["over"]["point"]:
                            best["total"]["over"] = {
                                "point": point,
                                "price": price,
                                "book": book_title,
                                "deeplink": ALLOWED_BOOKS[book_title]["deeplink"]
                            }

                    elif team == "Under":
                        consensus["total"]["under"].append(point)

                        if not best["total"]["under"] or point > best["total"]["under"]["point"]:
                            best["total"]["under"] = {
                                "point": point,
                                "price": price,
                                "book": book_title,
                                "deeplink": ALLOWED_BOOKS[book_title]["deeplink"]
                            }

    edges = {
        "spread": {},
        "moneyline": {},
        "total": {}
    }

    for team, spread in best["spread"].items():
        avg = mean(consensus["spread"][team])
        edges["spread"][team] = round(spread["point"] - avg, 2)

    for team, ml in best["moneyline"].items():
        avg = mean(consensus["moneyline"][team])
        edges["moneyline"][team] = int(ml["price"] - avg)

    edges["total"]["over"] = (
        round(best["total"]["over"]["point"] - mean(consensus["total"]["over"]), 2)
        if best["total"]["over"] else None
    )

    edges["total"]["under"] = (
        round(best["total"]["under"]["point"] - mean(consensus["total"]["under"]), 2)
        if best["total"]["under"] else None
    )

    teams = {
        "home": game.get("home_team"),
        "away": game.get("away_team")
    }

    return {
        "game_id": game_id,
        "league": league,
        "teams": teams,
        "best_lines": best,
        "edges": edges
    }