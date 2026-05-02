from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
import mimetypes
from typing import Any

class VoiceProvider:
    """
    Handles Speech-to-Text transcription using OpenAI Whisper API.
    """
    def __init__(self, api_key: str | None = None, api_base: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.api_base = api_base

    def transcribe(self, audio_content: bytes, filename: str = "audio.wav") -> str:
        """
        Transcribes the given audio content using Whisper.
        Falls back to mock if no API key is provided or if the call fails.
        """
        if not self.api_key:
            return "[Transcribed Voice Message] Hello doctor, I'm here to discuss the latest clinical data."

        boundary = "----VoiceTranscriptionBoundary"
        parts: list[Any] = []
        
        # Model parameter
        parts.append(f"--{boundary}")
        parts.append('Content-Disposition: form-data; name="model"')
        parts.append("")
        parts.append("whisper-1")
        
        # File parameter
        parts.append(f"--{boundary}")
        parts.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"')
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        parts.append(f"Content-Type: {content_type}")
        parts.append("")
        parts.append(audio_content)
        
        parts.append(f"--{boundary}--")
        parts.append("")

        body = b""
        for part in parts:
            if isinstance(part, str):
                body += part.encode("utf-8") + b"\r\n"
            else:
                body += part + b"\r\n"

        url = f"{self.api_base.rstrip('/')}/audio/transcriptions"
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=30.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return str(payload.get("text", "")).strip()
        except Exception as exc:
            # Fallback for Alpha runtime robustness
            return f"[Transcription Failed: {exc}] Hello doctor, I'm here to discuss the latest clinical data."

def build_voice_provider() -> VoiceProvider:
    """
    Builds the VoiceProvider using environment variables.
    """
    # Prioritize specific voice key, fallback to general model key
    api_key = os.getenv("MR_RUNTIME_VOICE_API_KEY") or os.getenv("MR_RUNTIME_MODEL_API_KEY")
    api_base = os.getenv("MR_RUNTIME_VOICE_API_BASE", "https://api.openai.com/v1")
    
    return VoiceProvider(api_key=api_key, api_base=api_base)
