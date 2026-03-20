import os
import sys

try:
    from openai import OpenAI
except ImportError:
    print("The 'openai' package is not installed.")
    print("Please install it running: pip install openai")
    sys.exit(1)

# Configuration: Adjust these for your local instance
APP_ID = "1" # Or your app slug, e.g. "my-app"
BASE_URL = f"http://localhost:8000/public/v1/app/{APP_ID}/openai/v1"
API_KEY = os.environ.get("MATTINAI_API_KEY", "YOUR_API_KEY_HERE")
MODEL_ID = "1"  # ID of a memoryless agent

def main():
    print(f"Initializing OpenAI client with BASE_URL: {BASE_URL}")
    client = OpenAI(
        base_url=BASE_URL,
        api_key=API_KEY
    )

    print("\n--- Testing GET /models ---")
    try:
        models = client.models.list()
        print("Available models:")
        for m in models:
            print(f" - {m.id} (Owned by: {m.owned_by})")
    except Exception as e:
        print(f"Error fetching models: {e}")

    print("\n--- Testing POST /chat/completions (Standard) ---")
    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is MattinAI?"}
            ],
            temperature=0.7
        )
        print("Response Usage:", response.usage)
        print("\nAssistant:")
        print(response.choices[0].message.content)
    except Exception as e:
        print(f"Error in chat completion: {e}")

    print("\n--- Testing POST /chat/completions (Streaming) ---")
    try:
        stream = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Write a short poem about artificial intelligence."}
            ],
            stream=True
        )
        print("Assistant:")
        for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                content = chunk.choices[0].delta.content
                if content:
                    print(content, end="", flush=True)
        print() # Print final newline
    except Exception as e:
        print(f"Error in streaming chat completion: {e}")

if __name__ == "__main__":
    if API_KEY == "YOUR_API_KEY_HERE":
        print("⚠️ WARNING: Using default placeholder API_KEY.")
        print("Ensure you have set MATTINAI_API_KEY in your environment or updated the variable.")
        print("Continuing anyway...\n")
    main()
