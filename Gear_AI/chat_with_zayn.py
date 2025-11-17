import os
import time
import sqlite3
import logging
from typing import Dict, Any, Optional, List

import google.generativeai as genai
from dotenv import load_dotenv
from pypdf import PdfReader

# -------------------- SETUP --------------------
load_dotenv(override=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DB_PATH = "chat_history.db"

_BANNED_KEYWORDS = [
    "hack", "crack", "bypass", "phish", "exploit", "malware",
    "keylogger", "unauthorized", "unauthorised", "steal", "breach"
]


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


def generate_response(user_id: str, session_id: str, query: str, file_path: Optional[str] = None, model_name: str = "gemini-2.5-flash") -> Dict[str, Any]:
    """Generate Gemini model response, using chat history as context."""
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    # Consolidated log message for the request
    log_message = f"User={user_id}, Session={session_id}, Query='{query}', File={file_path or 'None'}"
    logging.info(log_message)

    # Check for unsafe content
    if _is_malicious_query(query):
        logging.warning("Blocked potentially malicious query.")
        return {
            "status": "blocked",
            "response": None,
            "message": "I can’t assist with unauthorized or harmful activities.",
            "user_id": user_id,
            "session_id": session_id,
            "timestamp": timestamp
        }

    # Extract content from PDF if provided
    file_context = ""
    # --- Start: File Processing Logic ---
    file_content_for_prompt = ""
    if file_path and os.path.exists(file_path):
        if file_path.lower().endswith(".pdf"):
            try:
                reader = PdfReader(file_path)
                pdf_text = "".join(page.extract_text() or "" for page in reader.pages)
                file_context = f"Here is the content from the uploaded PDF file:\n---\n{pdf_text}\n---\n\n"
                file_content_for_prompt = (
                    "The user has uploaded a PDF document. "
                    f"Use the following content from the document to answer the user's question:\n"
                    f"<document_content>\n{pdf_text}\n</document_content>\n\n"
                )
                if pdf_text.strip():
                 logging.info(f"✅ Extracted {len(pdf_text)} characters from {file_path}")
                else:
                 logging.warning(f"⚠️ No text extracted from {file_path}")
            except Exception as e:
                logging.error(f"Failed to read or parse PDF file {file_path}: {e}")
                return {"status": "error", "message": f"Could not process the PDF file: {e}"}
        else:
            logging.warning(f"Unsupported file type provided: {file_path}. Only PDF is supported.")

    # --- End: File Processing Logic ---
    
    # Load previous session context
    history = get_session_history(user_id, session_id)
    context_text = "\n".join([f"User: {h['query']}\nAssistant: {h['response']}" for h in history])

    
    if file_context:
    # Only include once and keep structure clean
       user_prompt_section = (
        f"User uploaded a PDF. Use its content below to answer.\n\n"
        f"--- PDF Content Start ---\n{file_context}\n--- PDF Content End ---\n\n"
        f"User Question: {query}"
    )
    else:
       user_prompt_section = f"User Question: {query}"

    # Combine context + new query
    full_prompt = (
    f"{SYSTEM_PROMPT}\n\n"
    f"Previous chat history:\n{context_text}\n\n"
    f"{user_prompt_section}"
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
        q = input("You: ")
        if q.lower() in ["exit", "quit"]:
            break
        
    
        pdf_path_to_test = r"C:\Users\AKHILA\OneDrive\Desktop\aurora_all.pdf"          
        result = generate_response(user_id, session_id, q, file_path=pdf_path_to_test)
        print("Assistant:", result.get("response", result.get("message")))
