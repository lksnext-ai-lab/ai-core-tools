import requests
import logging
import os

from fastapi import HTTPException
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
        logger.error(f"Error extracting text from audio {audio_path}: {response.text}")
        raise HTTPException(status_code=500, detail="Audio transcription failed")

def turn_text_to_speech(text, language, output_path):
    """
    Convert the given text to speech using an external API and save the audio file.
    Returns the path to the generated audio file.
    """
    payload = {
        "text": text,
        "speaker": _speaker_for_language(language),
        "language": language,
        "api_id": os.getenv("ELHUYAR_API_ID"),
        "api_key": os.getenv("ELHUYAR_API_KEY")
    }

    response = requests.post("https://ttsneuronala.elhuyar.eus/api/standard", json=payload)

    if response.status_code == 200:
        with open(output_path + ".wav", "wb") as f:
            f.write(response.content)
        return output_path + ".wav"
    else:
        logger.error(f"Error converting text to speech for text '{text}': {response.text}")
        raise HTTPException(status_code=500, detail="Text-to-speech conversion failed")
    
def _speaker_for_language(language):
    if language == "es":
        return "female"
    elif language == "eu":
        return "female_high"
    else:
        return f"{language}_female_high"