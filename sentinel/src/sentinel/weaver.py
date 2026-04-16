import re
from datetime import datetime

# Regex to match ISO-8601 like timestamps at the beginning of log lines,
# or simple datetimes.
# Example: 2024-04-10T12:00:00Z or 2024-04-10 12:00:00.000
TIMESTAMP_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)

def extract_timestamp(line):
    match = TIMESTAMP_PATTERN.search(line)
    if match:
        ts_str = match.group("timestamp")
        # Replace space with T for consistency in lexicographical sorting
        return ts_str.replace(' ', 'T')
    return None

def synchronize_logs(raw_logs):
    """
    Takes a dictionary of {filename: [lines]}
    Extracts timestamps, normalizes them, and interleaves the logs chronologically.
    Returns a unified timeline list of dicts.
    """
    unified_timeline = []

    for filename, lines in raw_logs.items():
        current_ts = "0000-00-00T00:00:00" # fallback for lines without timestamp
        for line in lines:
            ts = extract_timestamp(line)
            if ts:
                current_ts = ts

            unified_timeline.append({
                "timestamp": current_ts,
                "source": filename,
                "message": line.strip()
            })

    # Sort chronologically using string comparison of ISO-8601
    unified_timeline.sort(key=lambda x: x["timestamp"])

    return unified_timeline
