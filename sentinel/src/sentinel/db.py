import json
import os

DB_FILE = ".sentinel_history.json"

def load_history():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load history DB: {e}")
        return {}

def save_history(history):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4)
    except Exception as e:
        print(f"Warning: Could not save history DB: {e}")

def record_test_run(test_name, status, error_signature=None):
    """
    Records a test run. Status should be "pass" or "fail".
    error_signature is an optional string representing the stack trace or error log.
    """
    history = load_history()

    if test_name not in history:
        history[test_name] = {
            "runs": [],
            "known_flakes": []
        }

    history[test_name]["runs"].append({
        "status": status,
        "error_signature": error_signature
    })

    # Keep only the last 10 runs
    if len(history[test_name]["runs"]) > 10:
        history[test_name]["runs"] = history[test_name]["runs"][-10:]

    save_history(history)

def get_test_history(test_name):
    history = load_history()
    return history.get(test_name, {})
