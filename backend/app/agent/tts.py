"""Server-side TTS using Google Text-to-Speech (gTTS).

Generates MP3 audio from text and returns it as a base64-encoded string
that the frontend can play using the HTML5 Audio API.
"""
import base64
import io
import logging
from typing import Optional
from gtts import gTTS

logger = logging.getLogger(__name__)

# Map language codes to gTTS language codes
LANG_MAP = {
    "en": "en",
    "hi": "hi",
    "ta": "ta",
}


def text_to_speech_base64(text: str, lang: str = "en") -> Optional[str]:
    """Convert text to speech and return base64-encoded MP3 audio.
    
    Args:
        text: The text to convert to speech.
        lang: Language code (en, hi, ta).
    
    Returns:
        Base64-encoded MP3 audio string, or None on failure.
    """
    if not text or not text.strip():
        return None

    # Map to gTTS language code
    gtts_lang = LANG_MAP.get(lang, "en")
    
    try:
        tts = gTTS(text=text, lang=gtts_lang, slow=False)
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        audio_b64 = base64.b64encode(audio_buffer.read()).decode("utf-8")
        logger.info(f"TTS generated: {len(audio_b64)} bytes for lang={gtts_lang}")
        return audio_b64
    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        return None
