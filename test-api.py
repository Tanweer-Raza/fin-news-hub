import requests
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("API_KEY_CREDITS")
# print(API_KEY)

url = "http://localhost:8000/generate"
headers = {
    "api-key": API_KEY,
    "Content-Type": "application/json"
}

body = {
    "prompt": "What is the capital of France?"
}
response = requests.post(url, headers=headers, json=body)
print(response.json())