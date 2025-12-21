from fastapi import FastAPI

app = FastAPI()

@app.get("/ping")
def ping():
    return {"status": "ok"}


@app.get("/games")
def get_games(league: str):
    return {
        "games": [
            {"id": "game1", "away": "Oklahoma", "home": "Alabama"},
            {"id": "game2", "away": "Texas", "home": "Georgia"}
        ]
    }


@app.get("/best-lines")
def best_lines(league: str, game_id: str):
    return {
        "game_id": game_id,
        "league": league,
        "best_lines": {
            "spread": {
                "team": "Alabama",
                "line": "-6.5",
                "book": "DraftKings"
            },
            "moneyline": {
                "team": "Oklahoma",
                "odds": "+220",
                "book": "FanDuel"
            },
            "total": {
                "line": "O 54.5",
                "book": "BetMGM"
            }
        }
    }
