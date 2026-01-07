from fastapi import FastAPI
import os
import requests
from statistics import mean

app = FastAPI()

API_KEY = os.getenv("ODDS_API_KEY")

BASE_URL = "https://api.the-odds-api.com/v4/sports"

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

ALLOWED_BOOKS = {
    "DraftKings": {
        "deeplink": "https://sportsbook.draftkings.com"
    },
    "FanDuel": {
        "deeplink": "https://sportsbook.fanduel.com"
    },
    "BetMGM": {
        "deeplink": "https://sports.betmgm.com"
    },
    "Caesars": {
        "deeplink": "https://www.caesars.com/sportsbook"
    },
    "bet365": {
        "deeplink": "https://www.bet365.com"
    }
}

KEY_NUMBERS = {
    "NFL": [3, 7, 10, 14],
    "NCAAF": [3, 7, 10, 14],
    "NBA": [3, 5, 7],
    "NCAAB": [3, 5, 7],
    "NHL": [1, 2],
    "MLB": [1, 2],
    "MLS": [1],
    "EPL": [1],
    "UFC": []
}


def key_number_flag(league: str, spread: float):
    keys = KEY_NUMBERS.get(league, [])
    abs_spread = abs(spread)

    if abs_spread in keys:
        return {"is_key": True, "type": "on_key", "strength": "strong"}

    for k in keys:
        if abs(abs_spread - k) == 0.5:
            return {"is_key": True, "type": "off_key", "strength": "medium"}

    return {"is_key": False, "type": None, "strength": None}


def is_better_ml(new, current):
    if current is None:
        return True
    if new > 0 and current > 0:
        return new > current
    if new < 0 and current < 0:
        return new > current  # -110 > -115
    return new > current


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/games")
def get_games(league: str):
    league = league.strip().upper()
    if league not in SPORT_MAP:
        return {"error": "Invalid league"}

    r = requests.get(
        f"{BASE_URL}/{SPORT_MAP[league]}/odds",
        params={
            "apiKey": API_KEY,
            "regions": "us",
            "markets": "h2h,spreads,totals",
            "oddsFormat": "american"
        }
    )
    r.raise_for_status()

    games = r.json()
    return {
        "games": [
            {
                "id": g.get("id"),
                "away": g.get("away_team"),
                "home": g.get("home_team"),
                "commence_time": g.get("commence_time")
            }
            for g in games
        ]
    }


@app.get("/best-lines")
def best_lines(league: str, game_id: str):
    league = league.upper()
    if league not in SPORT_MAP:
        return {"error": "Invalid league"}

    r = requests.get(
        f"{BASE_URL}/{SPORT_MAP[league]}/odds",
        params={
            "apiKey": API_KEY,
            "regions": "us",
            "markets": "spreads,h2h,totals",
            "oddsFormat": "american"
        }
    )
    r.raise_for_status()

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
            outcomes = market.get("outcomes", [])

            if key == "spreads":
                for o in outcomes:
                    team, point, price = o["name"], o["point"], o["price"]
                    cur = best["spread"].get(team)

                    take = (
                        not cur or
                        (point > 0 and point > cur["point"]) or
                        (point < 0 and point > cur["point"]) or
                        (point == cur["point"] and price > cur["price"])
                    )

                    if take:
                        best["spread"][team] = {
                            "point": point,
                            "price": price,
                            "book": book_title,
                            "deeplink": ALLOWED_BOOKS[book_title]["deeplink"],
                            "key_number": key_number_flag(league, point)
                        }

                    consensus["spread"].setdefault(team, []).append(point)

            elif key == "h2h":
                for o in outcomes:
                    team, price = o["name"], o["price"]
                    consensus["moneyline"].setdefault(team, []).append(price)

                    cur = best["moneyline"].get(team)
                    if is_better_ml(price, cur["price"] if cur else None):
                        best["moneyline"][team] = {
                            "price": price,
                            "book": book_title,
                            "deeplink": ALLOWED_BOOKS[book_title]["deeplink"]
                        }

            elif key == "totals":
                for o in outcomes:
                    side, point, price = o["name"], o["point"], o["price"]

                    if side == "Over":
                        consensus["total"]["over"].append(point)
                        if not best["total"]["over"] or point < best["total"]["over"]["point"]:
                            best["total"]["over"] = {
                                "point": point,
                                "price": price,
                                "book": book_title,
                                "deeplink": ALLOWED_BOOKS[book_title]["deeplink"]
                            }

                    elif side == "Under":
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

    for team, s in best["spread"].items():
        edges["spread"][team] = round(
            s["point"] - mean(consensus["spread"][team]), 2
        )

    for team, ml in best["moneyline"].items():
        edges["moneyline"][team] = int(
            ml["price"] - mean(consensus["moneyline"][team])
        )

    edges["total"]["over"] = (
        round(best["total"]["over"]["point"] - mean(consensus["total"]["over"]), 2)
        if best["total"]["over"] else None
    )

    edges["total"]["under"] = (
        round(best["total"]["under"]["point"] - mean(consensus["total"]["under"]), 2)
        if best["total"]["under"] else None
    )

    return {
        "game_id": game_id,
        "league": league,
        "teams": {
            "home": game.get("home_team"),
            "away": game.get("away_team")
        },
        "best_lines": best,
        "edges": edges
    }
    
from datetime import datetime, timezone
from statistics import mean

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

    summary_games = []

    for game in games:
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

                if key == "spreads":
                    for outcome in market.get("outcomes", []):
                        team = outcome.get("name")
                        point = outcome.get("point")
                        price = outcome.get("price")

                        current = best["spread"].get(team)
                        take = False

                        if not current:
                            take = True
                        elif point > 0 and point > current["point"]:
                            take = True
                        elif point < 0 and point > current["point"]:
                            take = True
                        elif point == current["point"] and price > current["price"]:
                            take = True

                        if take:
                            best["spread"][team] = {
                                "point": point,
                                "price": price,
                                "book": book_title
                            }

                        consensus["spread"].setdefault(team, []).append(point)

                elif key == "h2h":
                    for outcome in market.get("outcomes", []):
                        team = outcome.get("name")
                        price = outcome.get("price")

                        consensus["moneyline"].setdefault(team, []).append(price)

                        if team not in best["moneyline"] or price > best["moneyline"][team]["price"]:
                            best["moneyline"][team] = {
                                "price": price,
                                "book": book_title
                            }

                elif key == "totals":
                    for outcome in market.get("outcomes", []):
                        side = outcome.get("name")
                        point = outcome.get("point")
                        price = outcome.get("price")

                        if side == "Over":
                            consensus["total"]["over"].append(point)
                            if not best["total"]["over"] or point < best["total"]["over"]["point"]:
                                best["total"]["over"] = {
                                    "point": point,
                                    "price": price,
                                    "book": book_title
                                }

                        elif side == "Under":
                            consensus["total"]["under"].append(point)
                            if not best["total"]["under"] or point > best["total"]["under"]["point"]:
                                best["total"]["under"] = {
                                    "point": point,
                                    "price": price,
                                    "book": book_title
                                }

        summary_games.append({
            "away": game.get("away_team"),
            "home": game.get("home_team"),
            "commence_time": game.get("commence_time"),
            "best_lines": best
        })

    return {
        "league": league,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "games": summary_games
    }