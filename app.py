from fastapi import FastAPI
import os
import requests
from statistics import mean
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+

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

BOOK_PRIORITY = ["BetMGM", "DraftKings", "FanDuel", "Caesars", "bet365"]


def moneyline_value(odds):
    """
    Normalize American moneyline so higher is always better.
    +X: higher is better
    -X: closer to zero is better
    """
    if odds > 0:
        return odds
    else:
        return 100 / abs(odds) * 100


def better_price(new_price, current_price):
    """
    Returns True if new_price is better than current_price.
    Positive odds: higher is better
    Negative odds: closer to zero is better (less negative)
    """
    if current_price is None:
        return True
    if new_price > 0 and current_price > 0:
        return new_price > current_price
    elif new_price < 0 and current_price < 0:
        return new_price > current_price  # -150 > -250
    elif new_price > 0 and current_price < 0:
        return True
    elif new_price < 0 and current_price > 0:
        return False
    return False


@app.get("/league-summary")
def league_summary(league: str):
    league = league.upper()
    if league not in SPORT_MAP:
        return {"error": f"Invalid league '{league}'. Valid leagues: {list(SPORT_MAP.keys())}"}

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

    summary = []
    local_tz = ZoneInfo("America/Chicago")
    generated_at = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")).astimezone(local_tz)
    formatted_time = generated_at.strftime("%Y-%m-%d %I:%M %p %Z")

    for game in games:
        best = {"spread": {}, "moneyline": {}, "total": {"over": None, "under": None}}

        # Game info
        home = game.get("home_team")
        away = game.get("away_team")
        game_time_utc = game.get("commence_time")
        if game_time_utc:
            game_dt = datetime.fromisoformat(game_time_utc.replace("Z", "+00:00")).astimezone(local_tz)
            formatted_game_time = game_dt.strftime("%Y-%m-%d %I:%M %p %Z")
        else:
            formatted_game_time = "Unknown"

        for book in game.get("bookmakers", []):
            book_title = book.get("title")
            if book_title not in ALLOWED_BOOKS:
                continue
            deeplink = ALLOWED_BOOKS[book_title]["deeplink"]
            book_priority = BOOK_PRIORITY.index(book_title) if book_title in BOOK_PRIORITY else 999

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
                            # smaller abs spread preferred
                            if abs(point) < abs(current["point"]):
                                take = True
                            elif abs(point) == abs(current["point"]):
                                if better_price(price, current["price"]):
                                    take = True
                                elif price == current["price"]:
                                    current_priority = BOOK_PRIORITY.index(current["book"]) if current["book"] in BOOK_PRIORITY else 999
                                    if book_priority < current_priority:
                                        take = True
                        if take:
                            best["spread"][team] = {"point": point, "price": price, "book": book_title, "deeplink": deeplink}

                    # ---------- MONEYLINE ----------
                    elif key == "h2h":
                        current = best["moneyline"].get(team)
                        take = False
                        if not current:
                            take = True
                        else:
                            if better_price(price, current["price"]):
                                take = True
                            elif price == current["price"]:
                                current_priority = BOOK_PRIORITY.index(current["book"]) if current["book"] in BOOK_PRIORITY else 999
                                if book_priority < current_priority:
                                    take = True
                        if take:
                            best["moneyline"][team] = {"price": price, "book": book_title, "deeplink": deeplink}

                    # ---------- TOTALS ----------
                    elif key == "totals":
                        if team == "Over":
                            current = best["total"]["over"]
                            take = False
                            if not current:
                                take = True
                            elif point < current["point"]:
                                take = True
                            elif point == current["point"]:
                                if better_price(price, current["price"]):
                                    take = True
                                elif price == current["price"]:
                                    current_priority = BOOK_PRIORITY.index(current["book"]) if current["book"] in BOOK_PRIORITY else 999
                                    if book_priority < current_priority:
                                        take = True
                            if take:
                                best["total"]["over"] = {"point": point, "price": price, "book": book_title, "deeplink": deeplink}

                        elif team == "Under":
                            current = best["total"]["under"]
                            take = False
                            if not current:
                                take = True
                            elif point > current["point"]:
                                take = True
                            elif point == current["point"]:
                                if better_price(price, current["price"]):
                                    take = True
                                elif price == current["price"]:
                                    current_priority = BOOK_PRIORITY.index(current["book"]) if current["book"] in BOOK_PRIORITY else 999
                                    if book_priority < current_priority:
                                        take = True
                            if take:
                                best["total"]["under"] = {"point": point, "price": price, "book": book_title, "deeplink": deeplink}

        summary.append({
            "game_id": game.get("id"),
            "teams": {"home": home, "away": away},
            "game_time": formatted_game_time,
            "best_lines": best
        })

    return {
        "league": league,
        "generated_at": formatted_time,
        "games": summary
    }