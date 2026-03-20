import os
import requests

# Set these parameters according to your local instance
BASE_URL = "http://localhost:8000/public/v1/app/1/openai/v1"
API_KEY = "YOUR_API_KEY_HERE"  # Use the app API key
MODEL_ID = "1"  # ID of a memoryless agent

def test_models():
    print("Testing GET /models...")
    response = requests.get(
        f"{BASE_URL}/models",
        headers={"Authorization": f"Bearer {API_KEY}"}
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(response.json())
    else:
        print(response.text)
    print("-" * 50)

def test_chat_completion(stream=False):
    print(f"Testing POST /chat/completions (stream={stream})...")
    payload = {
        "model": MODEL_ID,
        "messages": [
            {"role": "user", "content": "What is MattinAI?"}
        ],
        "stream": stream
    }
    response = requests.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json=payload,
        stream=stream
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        if stream:
            for line in response.iter_lines():
                if line:
                    print(line.decode('utf-8'))
        else:
            print(response.json())
    else:
        print(response.text)
    print("-" * 50)

if __name__ == "__main__":
    test_models()
    test_chat_completion(stream=False)
    test_chat_completion(stream=True)
