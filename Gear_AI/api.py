import os
import shutil
import logging
from typing import Optional

from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse

from . import chat_with_zayn
from pydantic import BaseModel

UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(
    title="Chatbot API",
    description="API for interacting with chatbot and uploaded documents",
    version="1.0.0",
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


@app.on_event("startup")
async def startup_event():
    logging.info("Initializing backend...")
    chat_with_zayn.init_db()
    chat_with_zayn.configure_api()
    logging.info("Startup complete.")


class ChatResponse(BaseModel):
    status: str
    response: Optional[str] = None
    message: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    timestamp: Optional[str] = None


@app.post("/chat", response_model=ChatResponse)
async def handle_chat(
    user_id: str = Form(...),
    session_id: str = Form(...),
    query: str = Form(...),
    file: Optional[UploadFile] = File(None),
):
    file_path = None
    try:
        # ✅ Save uploaded file temporarily
        if file and file.filename:
            if not file.filename.lower().endswith(".pdf"):
                raise HTTPException(status_code=400, detail="Only PDF files are supported")

            temp_file_path = os.path.join(UPLOAD_DIR, file.filename)
            with open(temp_file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            file_path = os.path.abspath(temp_file_path)
            logging.info(f"✅ Uploaded file saved: {file_path}")

        #  Call backend logic
        result = chat_with_zayn.generate_response(
            user_id=user_id,
            session_id=session_id,
            query=query,
            file_path=file_path
        )

        return result  

    except Exception as e:
        logging.exception("Error occurred in /chat endpoint")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

    finally:
        if file_path and os.path.exists(file_path):
            logging.info(f"Keeping {file_path} for debugging (disable cleanup for now)")
            #os.remove(file_path)  # uncomment after testing

 # -------------------- FRONTEND ROUTE --------------------

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():

    current_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(current_dir, "index.html"), "r", encoding="utf-8") as f:
        return f.read()
    
  # ---------------- Endpoint to fetch chat history---------
@app.get("/history")
async def get_history(user_id: str, session_id: str):
    try:
        history = chat_with_zayn.get_session_history(user_id, session_id)
        if not history:
            return {"history": []}
        return {"history": history}
    except Exception as e:
        return {"error": str(e)}

