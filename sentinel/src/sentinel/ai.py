import os
import json
import google.generativeai as genai

def analyze_failure(timeline, history, api_key):
    """
    Sends the chronologically synchronized timeline and test history to Gemini for analysis.
    Returns a dictionary with the analysis results.
    """
    genai.configure(api_key=api_key)

    # We use a relatively stable model, gemini-1.5-pro, suitable for large contexts.
    # If not available or needed, we can fall back to gemini-1.5-flash.
    model = genai.GenerativeModel('gemini-1.5-pro')

    # Truncate timeline if it's too massive, just to be safe.
    # Take the last 5000 lines, as failures usually happen near the end.
    if len(timeline) > 5000:
         timeline = timeline[-5000:]

    timeline_str = "\n".join([f"[{t['timestamp']}] {t['source']}: {t['message']}" for t in timeline])

    history_str = "No historical context available."
    if history and history.get("runs"):
        history_str = json.dumps(history["runs"], indent=2)

    prompt = f"""
    You are an AI diagnostic expert analyzing test failures for the UDMI (Universal Device Management Interface) system.
    Below is a chronologically synchronized log combining test harness (Sequencer), device (Pubber), and system logs.
    You are also provided with the historical pass/fail run history for this test suite.

    Analyze these logs and history to determine the root cause of the test failure.
    If the history shows inconsistent failures without code changes, it is more likely a 'flake'.
    If the failure is deterministic, it is a 'hard_failure'.

    Respond STRICTLY with a valid JSON object matching this schema:
    {{
        "root_cause": "A detailed explanation of why the test failed.",
        "component_at_fault": "The specific component (e.g., 'sequencer', 'pubber', 'udmis', 'mosquitto') responsible for the failure.",
        "classification": "Either 'hard_failure' or 'flake'",
        "confidence": "A number from 0.0 to 1.0 indicating your confidence in this diagnosis"
    }}

    Do not include any markdown formatting around the JSON (like ```json ... ```), just output the raw JSON string.

    Historical Run Context:
    {history_str}

    Logs:
    {timeline_str}
    """

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Clean up in case Gemini added markdown despite instructions
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]

        return json.loads(text.strip())
    except Exception as e:
        print(f"Error querying Gemini: {e}")
        return {
            "root_cause": f"Failed to analyze with Gemini: {e}",
            "component_at_fault": "unknown",
            "classification": "unknown",
            "confidence": 0.0
        }
