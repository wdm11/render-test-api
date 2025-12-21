from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"status": "root ok"}

@app.get("/ping")
def ping():
    return {"status": "ping ok"}

@app.get("/games")
def games(league: str):
    return {
        "games": [
            {"id": "game1", "away": "Oklahoma", "home": "Alabama"}
        ]
    }

@app.get("/best-lines")
def best_lines(league: str, game_id: str):
    return {
        "league": league,
        "game_id": game_id,
        "message": "best-lines endpoint works"
    }
