import os
import time
import sqlite3
import logging
from typing import Dict, Any, Optional, List

import google.generativeai as genai
from dotenv import load_dotenv

# -------------------- SETUP --------------------
load_dotenv(override=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DB_PATH = "chat_history.db"

_BANNED_KEYWORDS = [
    "hack", "crack", "bypass", "phish", "exploit", "malware",
    "keylogger", "unauthorized", "unauthorised", "steal", "breach"
]


# -------------------- DATABASE FUNCTIONS --------------------
def init_db():
    """Initialize SQLite database for storing chat history."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            session_id TEXT,
            query TEXT,
            response TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_to_history(user_id: str, session_id: str, query: str, response: str):
    """Save a single chat record to SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO chat_history (user_id, session_id, query, response, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, session_id, query, response, time.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()


def get_session_history(user_id: str, session_id: str, limit: int = 5) -> List[Dict[str, str]]:
    """Retrieve last N chat records for the same session."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT query, response FROM chat_history
        WHERE user_id = ? AND session_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (user_id, session_id, limit))
    rows = cursor.fetchall()
    conn.close()

    return [{"query": q, "response": r} for q, r in reversed(rows)]


# -------------------- AI MODEL FUNCTIONS --------------------
def configure_api(api_key: Optional[str] = None):
    """Configure the Google Generative AI API key."""
    key = api_key or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Missing GOOGLE_API_KEY environment variable.")
    genai.configure(api_key=key)
    logging.info("Gemini API configured successfully.")


def _is_malicious_query(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _BANNED_KEYWORDS)


def generate_response(user_id: str, session_id: str, query: str, model_name: str = "gemini-2.5-flash") -> Dict[str, Any]:
    """Generate Gemini model response, using chat history as context."""
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    logging.info(f"User={user_id}, Session={session_id}, Query={query}")

    # Check for unsafe content
    if _is_malicious_query(query):
        logging.warning("Blocked potentially malicious query.")
        return {
            "status": "blocked",
            "message": "I can’t assist with unauthorized or harmful activities.",
        }

    # Load previous session context
    history = get_session_history(user_id, session_id)
    context_text = "\n".join([f"User: {h['query']}\nAssistant: {h['response']}" for h in history])

    # Combine context + new query
    full_prompt = (
        f"Here is the conversation so far:\n{context_text}\n\n"
        f"Now the user asks: {query}"
    )

    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(full_prompt)
        text = getattr(response, "text", str(response))

        # Save to database
        save_to_history(user_id, session_id, query, text)

        return {
            "status": "ok",
            "user_id": user_id,
            "session_id": session_id,
            "timestamp": timestamp,
            "response": text
        }

    except Exception as e:
        logging.exception("Error while generating response.")
        return {"status": "error", "message": str(e)}


# -------------------- MAIN TEST --------------------
if __name__ == "__main__":
    init_db()
    configure_api()

    user_id = "user_001"
    session_id = "session_123"

    # Simulate user asking questions in same session
    queries = [
        "Hi, can you explain what Gemini AI is?",
        "How is it different from ChatGPT?",
        "Can you summarize our conversation so far?"
    ]

    for q in queries:
        result = generate_response(user_id, session_id, q)
        print("\nUser:", q)
        print("Assistant:", result.get("response", result.get("message")))
