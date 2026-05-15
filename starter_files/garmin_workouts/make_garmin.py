import json, os

UPCOMING = os.path.join(os.path.dirname(__file__), "upcoming")

def save_workout(workout: dict, filename: str) -> str:
    """Write Garmin workout JSON with ASCII-safe unicode escapes (required for Chrome importer)."""
    out = json.dumps(workout, ensure_ascii=True, separators=(",", ":"))
    path = os.path.join(UPCOMING, filename)
    with open(path, "w", encoding="ascii") as f:
        f.write(out)
    print(f"Saved: {path}")
    return path
