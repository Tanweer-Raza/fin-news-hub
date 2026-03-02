from fastapi import FastAPI, Depends, HTTPException, Header
from pydantic import BaseModel
import uvicorn
import os
import ollama
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY_CREDITS")

if not API_KEY:
    raise Exception("API_KEY_CREDITS not set in .env")

# print("API_KEY :", API_KEY)

API_KEY_CREDITS = {API_KEY: 5}

app = FastAPI()


class PromptRequest(BaseModel):
    prompt: str



def verify_api_key(api_key: str = Header(None)):
    if api_key not in API_KEY_CREDITS:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if API_KEY_CREDITS[api_key] <= 0:
        raise HTTPException(status_code=403, detail="Credits exhausted")

    API_KEY_CREDITS[api_key] -= 1
    print(api_key)
    return api_key

@app.post("/generate")
def generate(data: PromptRequest, api_key: str = Depends(verify_api_key)):

    response = ollama.chat(
        model='gemma3:1b',
        messages=[{'role': 'user', 'content': data.prompt}]
    )

    return {
        "response": response['message']['content'],
        "remaining_credits": API_KEY_CREDITS[api_key]
    }


if __name__ == "__main__":
    uvicorn.run(app, port=8000)

