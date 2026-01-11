from fastapi import FastAPI
import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from supabase import create_client, Client

app = FastAPI()

# ---------- SUPABASE CLIENT ----------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------- HELPERS ----------
def save_snapshot(game_id, market, side, line):
    if not line:
        return
    supabase.table("line_snapshots").insert({
        "game_id": game_id,
        "market": market,
        "side": side,
        "point": line.get("point"),
        "price": line.get("price"),
        "book": line.get("book"),
        "timestamp": datetime.utcnow().isoformat()
    }).execute()

def get_previous_snapshot(game_id, market, side):
    try:
        response = (
            supabase.table("line_snapshots")
            .select("point, price, book, timestamp")
            .eq("game_id", game_id)
            .eq("market", market)
            .eq("side", side)
            .order("timestamp", desc=True)
            .limit(2)
            .execute()
        )
        rows = response.data
        if rows and len(rows) >= 2:
            prev = rows[1]
            return prev["point"], prev["price"], prev["book"]
    except Exception as e:
        print("Supabase fetch error:", e)
    return None, None, None

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
    "DraftKings": {"key": "draftkings", "deeplink": "https://sportsbook.draftkings.com"},
    "FanDuel": {"key": "fanduel", "deeplink": "https://sportsbook.fanduel.com"},
    "BetMGM": {"key": "betmgm", "deeplink": "shortcuts://run-shortcut?name=Open_BetMGM"},
    "Caesars": {"key": "caesars", "deeplink": "shortcuts://run-shortcut?name=Open_Caesers"},
    "bet365": {"key": "bet365", "deeplink": "shortcuts://run-shortcut?name=Open_bet365"}
}

BOOK_PRIORITY = ["BetMGM", "DraftKings", "FanDuel", "Caesars", "bet365"]

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

def compute_movement(current, previous, market):
    prev_point, prev_price, prev_book = previous
    point_move = 0
    price_move = 0
    book_move = False

    if market in ("spread", "total"):
        if current.get("point") is not None and prev_point is not None:
            point_move = round(current["point"] - prev_point, 2)

    if prev_price is not None and current.get("price") is not None:
        price_move = current["price"] - prev_price

    if prev_book is not None and current.get("book") is not None:
        if current["book"] != prev_book:
            book_move = True

    if point_move == 0 and price_move == 0 and not book_move:
        return "➖ No change"

    emoji = "📈" if (point_move > 0 or price_move > 0) else "📉"
    parts = []

    if point_move != 0:
        parts.append(f"{'+' if point_move > 0 else ''}{point_move} pts")
    if price_move != 0:
        parts.append(f"{'+' if price_move > 0 else ''}{price_move}¢")
    if book_move:
        parts.append(f"{prev_book} → {current['book']}")

    return f"{emoji} " + " / ".join(parts)

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
                "regions": "us",
                "markets": "spreads,h2h,totals",
                "oddsFormat": "american"
            },
            timeout=10
        )
        r.raise_for_status()
    except requests.RequestException as e:
        return {"error": " Odds API error ", "details": str(e)}

    games = r.json()
    summary = []

    local_tz = ZoneInfo("America/Chicago")
    generated_at = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")).astimezone(local_tz)
    formatted_time = generated_at.strftime("%Y-%m-%d %I:%M %p %Z")

    for game in games:
        best = {"spread": {}, "moneyline": {}, "total": {"over": None, "under": None}}

        home = game.get("home_team")
        away = game.get("away_team")
        game_time_utc = game.get("commence_time")
        if game_time_utc:
            game_dt = datetime.fromisoformat(game_time_utc.replace("Z", "+00:00")).astimezone(local_tz)
            formatted_game_time = game_dt.strftime("%Y-%m-%d %I:%M %p %Z")
        else:
            formatted_game_time = "Unknown"

        # ---------- BUILD BEST LINES ----------
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
                        elif point != current["point"]:
                            if point > 0 and current["point"] > 0 and point > current["point"]:
                                take = True
                            elif point < 0 and current["point"] < 0 and abs(point) < abs(current["point"]):
                                take = True
                        else:
                            if better_price(price, current["price"]):
                                take = True
                            elif price == current["price"]:
                                if book_priority < BOOK_PRIORITY.index(current["book"]):
                                    take = True
                        if take:
                            best["spread"][team] = {"point": point, "price": price, "book": book_title, "deeplink": deeplink}

                    # ---------- MONEYLINE ----------
                    elif key == "h2h":
                        current = best["moneyline"].get(team)
                        take = False
                        if not current:
                            take = True
                        elif better_price(price, current["price"]):
                            take = True
                        elif price == current["price"]:
                            if book_priority < BOOK_PRIORITY.index(current["book"]):
                                take = True
                        if take:
                            best["moneyline"][team] = {"price": price, "book": book_title, "deeplink": deeplink}

                    # ---------- TOTALS ----------
                    elif key == "totals":
                        if team == "Over":
                            current = best["total"]["over"]
                            take = False
                            if not current or point < current["point"]:
                                take = True
                            elif point == current["point"]:
                                if better_price(price, current["price"]):
                                    take = True
                                elif price == current["price"]:
                                    if book_priority < BOOK_PRIORITY.index(current["book"]):
                                        take = True
                            if take:
                                best["total"]["over"] = {"point": point, "price": price, "book": book_title, "deeplink": deeplink}
                        elif team == "Under":
                            current = best["total"]["under"]
                            take = False
                            if not current or point > current["point"]:
                                take = True
                            elif point == current["point"]:
                                if better_price(price, current["price"]):
                                    take = True
                                elif price == current["price"]:
                                    if book_priority < BOOK_PRIORITY.index(current["book"]):
                                        take = True
                            if take:
                                best["total"]["under"] = {"point": point, "price": price, "book": book_title, "deeplink": deeplink}

        game_id = f"{home}__{away}__{game_time_utc}"

        # ---------- MOVEMENT + SNAPSHOTS ----------
        for team, line in best["spread"].items():
            previous = get_previous_snapshot(game_id, "spread", team)
            line["note"] = compute_movement(line, previous, "spread")
            save_snapshot(game_id, "spread", team, line)

        for team, line in best["moneyline"].items():
            previous = get_previous_snapshot(game_id, "moneyline", team)
            line["note"] = compute_movement(line, previous, "moneyline")
            save_snapshot(game_id, "moneyline", team, line)

        if best["total"]["over"]:
            previous = get_previous_snapshot(game_id, "total", "Over")
            best["total"]["over"]["note"] = compute_movement(best["total"]["over"], previous, "total")
            save_snapshot(game_id, "total", "Over", best["total"]["over"])

        if best["total"]["under"]:
            previous = get_previous_snapshot(game_id, "total", "Under")
            best["total"]["under"]["note"] = compute_movement(best["total"]["under"], previous, "total")
            save_snapshot(game_id, "total", "Under", best["total"]["under"])

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
    