from fastapi import FastAPI
import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

app = FastAPI()

# ---------- CONFIG ----------
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
    "draftkings": {
        "title": "DraftKings",
        "deeplink": "https://sportsbook.draftkings.com"
    },
    "fanduel": {
        "title": "FanDuel",
        "deeplink": "https://sportsbook.fanduel.com"
    },
    "betmgm": {
        "title": "BetMGM",
        "deeplink": "shortcuts://run-shortcut?name=Open_BetMGM"
    },
    "caesars": {
        "title": "Caesars",
        "deeplink": "shortcuts://run-shortcut?name=Open_Caesers"
    },
    "williamhill_us": {
        "title": "Caesars",
        "deeplink": "shortcuts://run-shortcut?name=Open_Caesers"
    },
    "bet365": {
        "title": "bet365",
        "deeplink": "shortcuts://run-shortcut?name=Open_bet365"
    }
}

BOOK_PRIORITY = ["betmgm", "draftkings", "fanduel", "caesars", "williamhill_us", "bet365"]

# ---------- HELPERS ----------
def better_price(new_price, current_price):
    if current_price is None:
        return True
    if new_price > 0 and current_price > 0:
        return new_price > current_price
    if new_price < 0 and current_price < 0:
        return new_price > current_price
    if new_price > 0 and current_price < 0:
        return True
    return False


# ---------- ENDPOINT ----------
@app.get("/league-summary")
def league_summary(league: str):

    league = league.upper()
    if league not in SPORT_MAP:
        return {"error": f"Invalid league '{league}'"}

    sport = SPORT_MAP[league]

    try:
        r = requests.get(
            f"{BASE_URL}/{sport}/odds",
            params={
                "apiKey": API_KEY,
                "regions": "us,us2,eu",
                "markets": "spreads,h2h,totals",
                "bookmakers": "draftkings,fanduel,betmgm,caesars,bet365",
                "oddsFormat": "american"
            },
            timeout=10
        )
        r.raise_for_status()

    except requests.RequestException as e:
        return {"error": "Odds API error", "details": str(e)}

    games = r.json()
    summary = []

    local_tz = ZoneInfo("America/Chicago")
    generated_at = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")).astimezone(local_tz)
    formatted_time = generated_at.strftime("%Y-%m-%d %I:%M %p %Z")

    for game in games:

        best = {
            "spread": {},
            "moneyline": {},
            "total": {"over": None, "under": None}
        }

        home = game.get("home_team")
        away = game.get("away_team")

        game_time_utc = game.get("commence_time")

        if game_time_utc:
            game_dt = datetime.fromisoformat(
                game_time_utc.replace("Z", "+00:00")
            ).astimezone(local_tz)

            formatted_game_time = game_dt.strftime("%Y-%m-%d %I:%M %p %Z")
        else:
            formatted_game_time = "Unknown"

        # ---------- BUILD BEST LINES ----------
        for book in game.get("bookmakers", []):

            book_key = book.get("key")

            if book_key not in ALLOWED_BOOKS:
                continue

            book_title = ALLOWED_BOOKS[book_key]["title"]
            deeplink = ALLOWED_BOOKS[book_key]["deeplink"]

            book_priority = BOOK_PRIORITY.index(book_key)

            for market in book.get("markets", []):

                key = market.get("key")

                for outcome in market.get("outcomes", []):

                    team = outcome.get("name")
                    point = outcome.get("point")
                    price = outcome.get("price")

                    # ---------- SPREADS ----------
                    if key == "spreads":

                        current = best["spread"].get(team)
                        take = False

                        if not current:
                            take = True

                        else:

                            current_point = current["point"]

                            if team == home:
                                if abs(point) < abs(current_point):
                                    take = True
                                elif point == current_point and better_price(price, current["price"]):
                                    take = True

                            else:
                                if point > current_point:
                                    take = True
                                elif point == current_point and better_price(price, current["price"]):
                                    take = True

                            if not take and point == current_point and price == current["price"]:
                                if book_priority < BOOK_PRIORITY.index(current["book_key"]):
                                    take = True

                        if take:
                            best["spread"][team] = {
                                "point": point,
                                "price": price,
                                "book": book_title,
                                "book_key": book_key,
                                "deeplink": deeplink
                            }

                    # ---------- MONEYLINE ----------
                    elif key == "h2h":

                        current = best["moneyline"].get(team)
                        take = False

                        if not current:
                            take = True

                        elif better_price(price, current["price"]):
                            take = True

                        elif price == current["price"]:
                            if book_priority < BOOK_PRIORITY.index(current["book_key"]):
                                take = True

                        if take:
                            best["moneyline"][team] = {
                                "price": price,
                                "book": book_title,
                                "book_key": book_key,
                                "deeplink": deeplink
                            }

                    # ---------- TOTALS ----------
                    elif key == "totals":

                        if team == "Over":

                            current = best["total"]["over"]
                            take = False

                            if not current:
                                take = True

                            else:
                                if point < current["point"]:
                                    take = True
                                elif point == current["point"] and better_price(price, current["price"]):
                                    take = True

                            if take:
                                best["total"]["over"] = {
                                    "point": point,
                                    "price": price,
                                    "book": book_title,
                                    "book_key": book_key,
                                    "deeplink": deeplink
                                }

                        elif team == "Under":

                            current = best["total"]["under"]
                            take = False

                            if not current:
                                take = True

                            else:
                                if point > current["point"]:
                                    take = True
                                elif point == current["point"] and better_price(price, current["price"]):
                                    take = True

                            if take:
                                best["total"]["under"] = {
                                    "point": point,
                                    "price": price,
                                    "book": book_title,
                                    "book_key": book_key,
                                    "deeplink": deeplink
                                }

        summary.append({
            "game_id": game.get("id"),
            "teams": {
                "home": home,
                "away": away
            },
            "game_time": formatted_game_time,
            "best_lines": best
        })

    return {
        "league": league,
        "generated_at": formatted_time,
        "games": summary
    }