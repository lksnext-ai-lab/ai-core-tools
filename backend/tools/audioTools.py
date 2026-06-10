import requests
import logging
import os

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

def extract_text_from_audio(audio_path, language) -> str:
    """
    Extract text from the given audio file using an external API.
    Returns the transcribed text.
    """
    payload = {
        "language": language,
        "api_id": os.getenv("ELHUYAR_API_ID"),
        "api_key": os.getenv("ELHUYAR_API_KEY")
    }

    with open(audio_path, "rb") as f:
        files = {
            "wav_file": (audio_path, f, "audio/wav")
        }

        response = requests.post("https://api.aditu.eus/transcribe_segment", data=payload, files=files)

    text_output = None

    if response.status_code == 200:
        text_output = response.json().get("transcription")
        return text_output
    else:
        print("Error: ", response.text)
        logger.error(f"Error extracting text from audio {audio_path}: {response.text}")
        raise
