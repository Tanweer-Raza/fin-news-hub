from fastapi import FastAPI
import ollama

app = FastAPI()

@app.post("/generate")
def generate(prompt: str):
    response = ollama.chat(model='gemma3:1b', messages=[{'role': 'user', 'content': prompt}])
    return response['message']['content']


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="[IP_ADDRESS]", port=8000)
    
