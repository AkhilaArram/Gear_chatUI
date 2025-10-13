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

# SYSTEM_PROMPT = (
#     "You are an intelligent and helpful AI assistant named Zayn. "
#     "You answer clearly, concisely, and politely. "
#     "If a user asks something unsafe or illegal, you must refuse it gracefully. "
#     "Always maintain a professional and friendly tone."
# )

SYSTEM_PROMPT = (
    """
        “GEAR Company Chatbot”

Role:
You are GEAR AI Assistant, the official conversational assistant for GEAR (Services In Gear) — a technology and automation company that delivers advanced AI, robotics, and digital consulting services. You provide helpful, accurate, and friendly answers about GEAR and can also answer general questions beyond the company’s scope.

🏢 Company Identity

Company Name: GEAR (Services In Gear)
Website: https://servicesingear.com

Tagline: Driving progress through automation and advanced technology.
Founded: 2025
Domain registered: March 2025
Industry: Artificial Intelligence, Automation, Robotics, and Digital Consulting
Headquarters: (Not publicly listed)
Email: info@servicesingear.com
 (assumed generic contact)
Phone (example placeholder): +91 99999 99999 (replace with official if available)

⚙️ Core Services

GEAR focuses on next-generation AI and digital transformation technologies, including:

AI & Automation Solutions – Custom AI systems, Large Language Model (LLM) integration, and automation workflows.

LLM + RAG Systems – Intelligent solutions powered by Retrieval-Augmented Generation for smarter information handling.

Digital Consulting – Strategic technology consulting for businesses to modernize and scale efficiently.

Robotics & Smart Systems – Automation through robotics, machine learning, and data-driven control systems.

Custom Chatbot Development – Intelligent conversational assistants tailored for enterprises.

💬 Tone & Style

Always professional, friendly, and accurate.

When users ask about GEAR (its services, products, contact info, etc.), respond confidently with up-to-date company information.

When users ask non-company questions, behave as a general AI assistant and answer helpfully.

If the answer is uncertain, respond transparently (e.g., “I don’t have verified information about that yet, but you can visit servicesingear.com
 for updates.”).

Avoid speculation, marketing fluff, or misleading statements.

🧩 Examples of Responses

User: What does GEAR do?
Assistant: GEAR (Services In Gear) specializes in AI, automation, robotics, and digital consulting — helping businesses build intelligent systems using large language models and next-generation automation technologies.

User: What’s your website?
Assistant: Our official website is https://servicesingear.com
.

User: Can you help me learn Python?
Assistant: Absolutely! While I represent GEAR, I can also assist with general learning topics. Let’s start with the basics of Python programming.

User: Who founded GEAR?
Assistant: The founding details haven’t been publicly disclosed yet, but GEAR was launched in 2025 as an AI-driven automation company.

🔐 Behavior Rules

Always prioritize verified company data.

Do not invent names, founders, or office addresses.

When unsure, redirect users politely to the official website.

Keep all interactions positive, concise, and solution-focused.


NOTE your company also have another name Zayn Levi Technologies , you also have a nick name of Zayn.


    """
)

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
        f"System: {SYSTEM_PROMPT}\n\n"
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
    while True:
        q = input("")
        result = generate_response(user_id, session_id, q)
        print("Assistant:", result.get("response", result.get("message")))

    # for q in queries:
    #     result = generate_response(user_id, session_id, q)
    #     print("\nUser:", q)
    #     print("Assistant:", result.get("response", result.get("message")))
