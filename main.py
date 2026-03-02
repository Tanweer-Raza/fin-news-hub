from fastapi import FastAPI, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy import create_engine, text
import uvicorn
import os
import ollama
from dotenv import load_dotenv


# ================= LOAD ENV =================

load_dotenv()


DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

API_KEY = os.getenv("API_KEY_CREDITS")

if not API_KEY:
    raise Exception("API_KEY_CREDITS not set in .env")

API_KEY_CREDITS = {API_KEY: 20}


# ================= DATABASE =================

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def get_latest_articles(limit=5):
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT title, content, posted_on
            FROM articles
            ORDER BY posted_on DESC
            LIMIT :limit
        """), {"limit": limit}).fetchall()

        return [
            {
                "title": row[0],
                "content": row[1],
                "posted_on": str(row[2])
            }
            for row in rows
        ]


# ================= FASTAPI =================

app = FastAPI()


class PromptRequest(BaseModel):
    prompt: str


# ================= API KEY CHECK =================

def verify_api_key(api_key: str = Header(None)):
    if api_key not in API_KEY_CREDITS:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if API_KEY_CREDITS[api_key] <= 0:
        raise HTTPException(status_code=403, detail="Credits exhausted")

    API_KEY_CREDITS[api_key] -= 1
    return api_key


# ================= SUMMARIZE LATEST NEWS =================

@app.get("/summarize")
def summarize(api_key: str = Depends(verify_api_key)):

    articles = get_latest_articles(2)

    if not articles:
        raise HTTPException(status_code=404, detail="No articles found")

    combined_text = "\n\n".join(
        f"Title: {a['title']}\nContent: {a['content'][:1500]}"
        for a in articles
    )

    prompt = f"""
    Summarize the following latest financial news in simple language:

    {combined_text}
    """

    response = ollama.chat(
        model="gemma3:1b",
        messages=[{"role": "user", "content": prompt}]
    )

    return {
        "summary": response["message"]["content"],
        "remaining_credits": API_KEY_CREDITS[api_key]
    }


# ================= ASK QUESTION (RAG STYLE) =================

@app.post("/ask")
def ask_question(data: PromptRequest, api_key: str = Depends(verify_api_key)):

    articles = get_latest_articles(10)

    context = "\n\n".join(
        f"{a['title']}\n{a['content'][:2000]}"
        for a in articles
    )

    prompt = f"""
    Use the following news articles to answer the question.

    News Context:
    {context}

    Question:
    {data.prompt}

    Answer in simple clear language.
    """

    response = ollama.chat(
        model="gemma3:1b",
        messages=[{"role": "user", "content": prompt}]
    )

    return {
        "answer": response["message"]["content"],
        "remaining_credits": API_KEY_CREDITS[api_key]
    }


# ================= RUN =================

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)