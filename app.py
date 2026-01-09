from fastapi import FastAPI
import os
import requests
from statistics import mean
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+
import sqlite3
 
app = FastAPI()
 
# ---------- DATABASE ----------
DB_PATH = "lines.db"
 
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()
 
cursor.execute("""
CREATE TABLE IF NOT EXISTS line_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL,
    market TEXT NOT NULL,
    side TEXT NOT NULL,
    point REAL,
    price INTEGER,
    book TEXT,
    timestamp TEXT
)
""")
conn.commit()
 
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
    """
    Higher numeric value is always better.
    +250 > +150
    -150 > -250
    """
    if current_price is None:
        return True
    if new_price > 0 and current_price > 0:
        return new_price > current_price
    if new_price < 0 and current_price < 0:
        return new_price > current_price
    if new_price > 0 and current_price < 0:
        return True
    return False
 
 
def save_snapshot(game_id, market, side, line):
    if not line:
        return
 
    cursor.execute(
        """
        INSERT INTO line_snapshots
        (game_id, market, side, point, price, book, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            game_id,
            market,
            side,
            line.get("point"),
            line.get("price"),
            line.get("book"),
            datetime.utcnow().isoformat()
        )
    )
    conn.commit()
 
 
def get_previous_snapshot(game_id, market, side):
    cursor.execute(
        """
        SELECT point, price, book
        FROM line_snapshots
        WHERE game_id = ?
          AND market = ?
          AND side = ?
        ORDER BY timestamp DESC
        LIMIT 1 OFFSET 0
        """,
        (game_id, market, side)
    )
    return cursor.fetchone()
 

def compute_movement_all(current, previous, market, side):
    """
    Tracks all relevant movement:
    - Spread: point & price
    - Moneyline: price
    - Totals: point & price
    """
    if not current or not previous:
        return {
            "has_movement": False,
            "direction": None,
            "emoji": "",
            "summary": ""
        }

    # Determine what to compare based on market/side
    point_move = 0
    price_move = 0

    prev_point, prev_price, _ = previous

    if market in ["spread", "total"]:
        if current.get("point") is not None and prev_point is not None:
            point_move = round(current["point"] - prev_point, 2)

    if market in ["spread", "moneyline", "total"]:
        if prev_price is not None:
            price_move = current.get("price", 0) - prev_price

    if point_move == 0 and price_move == 0:
        return {
            "has_movement": False,
            "direction": None,
            "emoji": "",
            "summary": ""
        }

    # Determine overall direction
    direction = "up" if (point_move > 0 or price_move > 0) else "down"
    emoji = "📈" if direction == "up" else "📉"

    # Build human-readable summary
    parts = []
    if point_move != 0:
        parts.append(f"{'+' if point_move > 0 else ''}{point_move} pts")
    if price_move != 0:
        parts.append(f"{'+' if price_move > 0 else ''}{price_move}¢")

    return {
        "has_movement": True,
        "direction": direction,
        "emoji": emoji,
        "summary": ", ".join(parts)
    }
    
def build_movement_note(movement):
    if not movement or not movement.get("has_movement"):
        return ""

    parts = []

    if movement["direction"] == "up":
        emoji = "📈"
    elif movement["direction"] == "down":
        emoji = "📉"
    else:
        return ""

    if movement.get("point_move"):
        sign = "+" if movement["point_move"] > 0 else ""
        parts.append(f"{sign}{movement['point_move']} pts")

    if movement.get("price_move"):
        sign = "+" if movement["price_move"] > 0 else ""
        parts.append(f"{sign}{movement['price_move']}¢")

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
                    
                        # Better spread always wins
                        elif point != current["point"]:
                            # Underdog: higher number is better (+3.5 > +3)
                            if point > 0 and current["point"] > 0:
                                if point > current["point"]:
                                    take = True
                    
                            # Favorite: closer to zero is better (-3 > -3.5)
                            elif point < 0 and current["point"] < 0:
                                if abs(point) < abs(current["point"]):
                                    take = True
                    
                        # Same spread → compare price
                        else:
                            if better_price(price, current["price"]):
                                take = True
                            elif price == current["price"]:
                                if book_priority < BOOK_PRIORITY.index(current["book"]):
                                    take = True
                    
                        if take:
                            best["spread"][team] = {
                                "point": point,
                                "price": price,
                                "book": book_title,
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
                            if book_priority < BOOK_PRIORITY.index(current["book"]):
                                take = True
                        if take:
                            best["moneyline"][team] = {
                                "price": price,
                                "book": book_title,
                                "deeplink": deeplink
                            }
 
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
                                best["total"]["over"] = {
                                    "point": point,
                                    "price": price,
                                    "book": book_title,
                                    "deeplink": deeplink
                                }
 
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
                                best["total"]["under"] = {
                                    "point": point,
                                    "price": price,
                                    "book": book_title,
                                    "deeplink": deeplink
                                }

        game_id = game.get("id")
        
        # ---------- MOVEMENT + SNAPSHOTS ----------

        # Spreads
        for team, line in best["spread"].items():
            previous = get_previous_snapshot(game_id, "spread", team)
            movement = compute_movement(line, previous)
            line["movement"] = movement
            line["note"] = build_movement_note(movement)
            save_snapshot(game_id, "spread", team, line)
        
        # Moneyline
        for team, line in best["moneyline"].items():
            previous = get_previous_snapshot(game_id, "moneyline", team)
            movement = compute_movement(line, previous)
            line["movement"] = movement
            line["note"] = build_movement_note(movement)
            save_snapshot(game_id, "moneyline", team, line)
        
        # Totals
        if best["total"]["over"]:
            previous = get_previous_snapshot(game_id, "total", "Over")
            movement = compute_movement(best["total"]["over"], previous)
            best["total"]["over"]["movement"] = movement
            best["total"]["over"]["note"] = build_movement_note(movement)
            save_snapshot(game_id, "total", "Over", best["total"]["over"])

        if best["total"]["under"]:
            movement = compute_movement(best["total"]["under"], previous)
            best["total"]["under"]["movement"] = movement
            best["total"]["under"]["note"] = build_movement_note(movement)
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