from fastapi import FastAPI
import os
import requests
from statistics import mean
from datetime import datetime

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
    "DraftKings": {"key": "draftkings", "deeplink": "https://sportsbook.draftkings.com"},
    "FanDuel": {"key": "fanduel", "deeplink": "https://sportsbook.fanduel.com"},
    "BetMGM": {"key": "betmgm", "deeplink": "shortcuts://run-shortcut?name=Open_BetMGM"},
    "Caesars": {"key": "caesars", "deeplink": "shortcuts://run-shortcut?name=Open_Caesers"},
    "bet365": {"key": "bet365", "deeplink": "shortcuts://run-shortcut?name=Open_bet365"}
}

# Priority for tie-breakers
BOOK_PRIORITY = {
    "BetMGM": 0,
    "DraftKings": 1,
    "FanDuel": 2,
    "Caesars": 3,
    "bet365": 4
}

@app.get("/league-summary")
def league_summary(league: str):
    league = league.strip().upper()
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
        return {"error": "Failed to fetch odds", "details": str(e)}

    games = r.json()
    if not games:
        return {"error": "No games returned"}

    summaries = []

    for game in games:
        best = {"spread": {}, "moneyline": {}, "total": {"over": None, "under": None}}
        consensus = {"spread": {}, "moneyline": {}, "total": {"over": [], "under": []}}

        home = game.get("home_team")
        away = game.get("away_team")

        for book in game.get("bookmakers", []):
            book_title = book.get("title")
            if book_title not in ALLOWED_BOOKS:
                continue
            priority = BOOK_PRIORITY.get(book_title, 999)

            for market in book.get("markets", []):
                key = market.get("key")
                for outcome in market.get("outcomes", []):
                    team = outcome.get("name")
                    point = outcome.get("point")
                    price = outcome.get("price")

                    # -------- SPREADS --------
                    if key == "spreads":
                        current = best["spread"].get(team)
                        take = False
                        if not current:
                            take = True
                        elif point > 0 and point > current["point"]:
                            take = True
                        elif point < 0 and point > current["point"]:
                            take = True
                        # Tie breaker: price
                        elif point == current["point"] and price > current["price"]:
                            take = True
                        # Tie breaker: sportsbook priority
                        elif point == current["point"] and price == current["price"] and priority < BOOK_PRIORITY[current["book"]]:
                            take = True
                        if take:
                            best["spread"][team] = {
                                "point": point,
                                "price": price,
                                "book": book_title,
                                "deeplink": ALLOWED_BOOKS[book_title]["deeplink"]
                            }
                        consensus["spread"].setdefault(team, []).append(point)

                    # -------- MONEYLINE --------
                    elif key == "h2h":
                        current = best["moneyline"].get(team)
                        take = False
                        if not current:
                            take = True
                        else:
                            # Determine best moneyline (higher is better for + odds, closer to zero is better for - odds)
                            if (price > 0 and price > current["price"]) or (price < 0 and price > current["price"]):
                                take = True
                            elif price == current["price"] and priority < BOOK_PRIORITY[current["book"]]:
                                take = True
                        if take:
                            best["moneyline"][team] = {
                                "price": price,
                                "book": book_title,
                                "deeplink": ALLOWED_BOOKS[book_title]["deeplink"]
                            }
                        consensus["moneyline"].setdefault(team, []).append(price)

                    # -------- TOTALS --------
                    elif key == "totals":
                        if team == "Over":
                            current = best["total"]["over"]
                            take = False
                            if not current:
                                take = True
                            elif point < current["point"]:
                                take = True
                            # Tie breaker: price
                            elif point == current["point"] and price > current["price"]:
                                take = True
                            elif point == current["point"] and price == current["price"] and priority < BOOK_PRIORITY[current["book"]]:
                                take = True
                            if take:
                                best["total"]["over"] = {
                                    "point": point,
                                    "price": price,
                                    "book": book_title,
                                    "deeplink": ALLOWED_BOOKS[book_title]["deeplink"]
                                }
                            consensus["total"]["over"].append(point)
                        elif team == "Under":
                            current = best["total"]["under"]
                            take = False
                            if not current:
                                take = True
                            elif point > current["point"]:
                                take = True
                            # Tie breaker: price
                            elif point == current["point"] and price > current["price"]:
                                take = True
                            elif point == current["point"] and price == current["price"] and priority < BOOK_PRIORITY[current["book"]]:
                                take = True
                            if take:
                                best["total"]["under"] = {
                                    "point": point,
                                    "price": price,
                                    "book": book_title,
                                    "deeplink": ALLOWED_BOOKS[book_title]["deeplink"]
                                }
                            consensus["total"]["under"].append(point)

        summaries.append({
            "game_id": game.get("id"),
            "home_team": home,
            "away_team": away,
            "best_lines": best
        })

    return {
        "league": league,
        "summaries": summaries
    }