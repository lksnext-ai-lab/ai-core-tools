import os
import tempfile
import subprocess

from utils.logger import get_logger
from tools.audioTools import extract_text_from_audio

logger = get_logger(__name__)

class AudioTranscriptionService:
    """Service for handling audio transcription using an external API."""

    @staticmethod
    def convert_to_wav(audio_path: str) -> str:
        """
        Convert the input audio file to WAV format using ffmpeg.
        Returns the path to the converted WAV file.
        """

        wav_path = tempfile.mktemp(suffix=".wav")

        subprocess.run(
            [
                "ffmpeg",
                "-i",
                audio_path,
                "-ar", "16000",
                "-ac", "1",
                wav_path,
                "-y"
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        return wav_path
    
    @staticmethod
    async def transcribe_audio(audio_path: str, language: str) -> str:
        """
        Transcribe the given audio file to text.
        Returns the transcribed text.
        """
        wav_path = None

        try:
            if audio_path.lower().endswith(".wav"):
                wav_path = audio_path
            else:
                wav_path = AudioTranscriptionService.convert_to_wav(audio_path)
            
            text_output = extract_text_from_audio(wav_path, language)

            return text_output
        except Exception as e:
            logger.error(f"Error transcribing audio {audio_path}: {e}")
            raise
        finally:
            if (wav_path and wav_path != audio_path and os.path.exists(wav_path)):
                try:
                    os.remove(wav_path)
                    logger.info(f"Removed temporary WAV file {wav_path}")
                except Exception as e:
                    logger.error(f"Error removing temporary WAV file {wav_path}: {e}")