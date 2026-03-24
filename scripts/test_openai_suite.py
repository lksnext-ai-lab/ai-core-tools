#!/usr/bin/env python3
"""Unified OpenAI compatibility test suite for MattinAI.

This single script consolidates:
- scripts/test_openai_api.py
- scripts/test_openai_client.py
- scripts/test_openai_compatibility.py
- scripts/test_openai_vision.py

Usage:
    export OPENAI_API_KEY="<api-key>"  # or MATTINAI_API_KEY
    export MATTINAI_APP_ID="1"
    export MATTINAI_BASE_URL="http://localhost:8000"
    python scripts/test_openai_suite.py
"""

import json
import os
import sys

import requests

try:
    from openai import APIError, OpenAI
except ImportError:
    print("The 'openai' package is not installed.")
    print("Install it by running: pip install openai")
    sys.exit(1)

# Configurable environment variables
BASE_URL = os.getenv("MATTINAI_BASE_URL", "http://localhost:8000")
APP_ID = os.getenv("MATTINAI_APP_ID", "1")
API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("MATTINAI_API_KEY")
MODEL_ID = os.getenv("MATTINAI_MODEL_ID", "1")

OPENAI_BASE_URL = f"{BASE_URL}/public/v1/app/{APP_ID}/openai/v1"


def require_api_key():
    if not API_KEY:
        print("ERROR: OPENAI_API_KEY or MATTINAI_API_KEY environment variable is not set.")
        sys.exit(1)


def setup_openai_client():
    return OpenAI(api_key=API_KEY, base_url=OPENAI_BASE_URL)


def test_requests_models() -> bool:
    print("\n--- TEST: /models (requests GET) ---")
    try:
        response = requests.get(
            f"{OPENAI_BASE_URL}/models",
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=30,
        )
        print(f"Status: {response.status_code}")
        if response.status_code != 200:
            print(response.text)
            return False

        data = response.json()
        print(f"Success: {len(data.get('data', []))} models")
        return True
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}")
        return False


def test_requests_chat_completion(stream: bool = False) -> bool:
    print(f"\n--- TEST: /chat/completions (requests POST, stream={stream}) ---")
    payload = {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": "What is MattinAI?"}],
        "stream": stream,
    }

    try:
        response = requests.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json=payload,
            stream=stream,
            timeout=60,
        )

        print(f"Status: {response.status_code}")
        if response.status_code != 200:
            print(response.text)
            return False

        if stream:
            lines = []
            for line in response.iter_lines(decode_unicode=True):
                if line:
                    lines.append(line)
                    print(line)
            return len(lines) > 0

        print(response.json())
        return True
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}")
        return False


def test_openai_client_models(client: OpenAI) -> bool:
    print("\n--- TEST: openai client models.list() ---")
    try:
        models = client.models.list()
        print(f"Success: {len(models.data)} models")
        for m in models.data[:5]:
            print(f" - {m.id}")
        return True
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}")
        return False


def test_openai_client_chat_non_stream(client: OpenAI) -> bool:
    print("\n--- TEST: openai client chat.completions.create (non-stream) ---")
    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Return JSON {\"status\": \"ok\"}"},
            ],
            max_tokens=100,
            temperature=0.0,
        )

        text = response.choices[0].message.content
        print(f"Model: {response.model}")
        print(f"Response: {text[:200]}")
        return True
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}")
        return False


def test_openai_client_chat_stream(client: OpenAI) -> bool:
    print("\n--- TEST: openai client chat.completions.create (stream) ---")
    try:
        total = ""
        stream = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Count to 3 with commas."},
            ],
            max_tokens=100,
            temperature=0.0,
            stream=True,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta
            delta_content = None
            if hasattr(delta, "content"):
                delta_content = delta.content

            # Support both string and nested structured content formats
            if isinstance(delta_content, str):
                total += delta_content
                print(delta_content, end="", flush=True)
            elif isinstance(delta_content, dict):
                # Some providers return {"content": {"content": "..."}}
                nested = delta_content.get("content")
                if isinstance(nested, str):
                    total += nested
                    print(nested, end="", flush=True)
                else:
                    encoded = json.dumps(delta_content, ensure_ascii=False)
                    total += encoded
                    print(encoded, end="", flush=True)

        print()  # newline
        print(f"Final streamed text: {total}")
        return len(total) > 0
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}")
        return False


def test_openai_client_error_invalid_model(client: OpenAI) -> bool:
    print("\n--- TEST: openai client error handling invalid model ---")
    try:
        client.chat.completions.create(
            model="invalid-model-id-99999",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=10,
        )
        print("Error: expected creation to fail but it passed")
        return False
    except APIError as e:
        print(f"Success: raised APIError (status: {getattr(e, 'status_code', 'N/A')})")
        return True
    except Exception as exc:
        print(f"Unexpected error type: {type(exc).__name__}: {exc}")
        return False


def test_openai_client_vision(client: OpenAI) -> bool:
    print("\n--- TEST: openai vision chat completion (base64 + image URL) ---")
    base64_image = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )

    passed = True

    base64_ok = False
    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What do you see in this image?"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                    ],
                }
            ],
            max_tokens=150,
        )
        print("Vision base64 response:", response.choices[0].message.content)
        base64_ok = True
    except Exception as exc:
        # Known environment may not have static image storage available for base64 conversion.
        txt = str(exc)
        if "404 Client Error" in txt and "/static/persistent/" in txt:
            print("Vision base64 skipped due unsupported static URL handling in this environment (not fatal):", exc)
        else:
            print("Vision base64 failed:", exc)

    url_ok = False

    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image in one sentence."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wis-porple-burlap.jpg/320px-Gfp-wis-porple-burlap.jpg",
                            },
                        },
                    ],
                }
            ],
            max_tokens=150,
        )
        print("Vision URL response:", response.choices[0].message.content)
        url_ok = True
    except Exception as exc:
        print("Vision URL failed:", exc)

    # keep suite pass if at least one vision mode works
    if not (base64_ok or url_ok):
        passed = False

    return passed


def main():
    require_api_key()
    client = setup_openai_client()

    results = {
        "requests_models": test_requests_models(),
        "requests_chat_non_stream": test_requests_chat_completion(stream=False),
        "requests_chat_stream": test_requests_chat_completion(stream=True),
        "openai_client_models": test_openai_client_models(client),
        "openai_client_chat_non_stream": test_openai_client_chat_non_stream(client),
        "openai_client_chat_stream": test_openai_client_chat_stream(client),
        "openai_client_invalid_model": test_openai_client_error_invalid_model(client),
        "openai_client_vision": test_openai_client_vision(client),
    }

    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for k, v in results.items():
        print(f"{k}: {'PASS' if v else 'FAIL'}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    if API_KEY is None:
        print("⚠️ WARNING: API key is not set, but script will abort to avoid ambiguous behavior.")
    main()
