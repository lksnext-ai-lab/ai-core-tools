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
MODEL_ID = "1"  # ID of a memoryless agent WITH vision capabilities

# Small 1x1 transparent PNG encoded in base64
BASE64_IMAGE = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

def main():
    print(f"Initializing OpenAI client with BASE_URL: {BASE_URL}")
    client = OpenAI(
        base_url=BASE_URL,
        api_key=API_KEY
    )

    print("\n--- Testing POST /chat/completions (Vision with base64) ---")
    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What do you see in this image? Notice the colour or what is in it."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{BASE64_IMAGE}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=300
        )
        print("Response Usage:", response.usage)
        print("\nAssistant (Base64 Image):")
        print(response.choices[0].message.content)
    except Exception as e:
        print(f"Error in vision chat completion (base64): {e}")

    print("\n--- Testing POST /chat/completions (Vision with URL) ---")
    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe the content of this image in one short sentence."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wis-porple-burlap.jpg/320px-Gfp-wis-porple-burlap.jpg"
                            }
                        }
                    ]
                }
            ],
            max_tokens=300
        )
        print("Response Usage:", response.usage)
        print("\nAssistant (URL Image):")
        print(response.choices[0].message.content)
    except Exception as e:
        print(f"Error in vision chat completion (url): {e}")

if __name__ == "__main__":
    if API_KEY == "YOUR_API_KEY_HERE":
        print("⚠️ WARNING: Using default placeholder API_KEY.")
        print("Ensure you have set MATTINAI_API_KEY in your environment or updated the variable.")
        print("Continuing anyway...\n")
    main()
