"""Tool for transcribing audio files using Azure Speech Services."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

logger = logging.getLogger(__name__)


class TranscribeAudioParams(BaseModel):
    """Parameters for the transcribe_audio tool."""

    container: str = Field(..., description="Azure Blob Storage container name.")
    path: str = Field(..., description="Blob path to the audio file (WAV, MP3, etc.).")
    language: str = Field(
        "en-US",
        description="Language code for transcription (e.g. 'en-US', 'es-ES').",
    )


@define_tool(
    name="transcribe_audio",
    description=(
        "Transcribe audio files using Azure Speech Services. Returns the full "
        "transcription text and timestamped segments. Supports WAV, MP3, and "
        "other common audio formats."
    ),
    parameters_model=TranscribeAudioParams,
)
async def transcribe_audio(
    params: TranscribeAudioParams, context: dict
) -> dict[str, Any]:
    """Download an audio file and transcribe it using Azure Speech Services."""
    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError:
        return {
            "error": (
                "Azure Speech SDK (azure-cognitiveservices-speech) is not installed. "
                "Audio transcription is not available."
            ),
            "filename": params.path,
        }

    settings = context.get("settings")
    speech_key = getattr(settings, "AZURE_SPEECH_KEY", "") if settings else ""
    speech_region = getattr(settings, "AZURE_SPEECH_REGION", "") if settings else ""

    if not speech_key or not speech_region:
        return {
            "error": (
                "Azure Speech Services is not configured. "
                "Set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION environment variables."
            ),
            "filename": params.path,
        }

    try:
        import asyncio
        import tempfile
        import os

        blob = context["blob"]
        logger.info("Downloading audio blob %s/%s", params.container, params.path)
        audio_bytes: bytes = await blob.download_blob(params.container, params.path)

        # Write to temp file since the Speech SDK needs a file path
        suffix = os.path.splitext(params.path)[1] or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            speech_config = speechsdk.SpeechConfig(
                subscription=speech_key, region=speech_region
            )
            speech_config.speech_recognition_language = params.language
            audio_config = speechsdk.AudioConfig(filename=tmp_path)

            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config, audio_config=audio_config
            )

            all_results: list[dict[str, Any]] = []
            done_event = asyncio.Event()

            def on_recognized(evt):
                if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                    all_results.append({
                        "text": evt.result.text,
                        "offset": evt.result.offset / 10_000_000,  # ticks to seconds
                        "duration": evt.result.duration / 10_000_000,
                    })

            def on_session_stopped(evt):
                done_event.set()

            def on_canceled(evt):
                done_event.set()

            recognizer.recognized.connect(on_recognized)
            recognizer.session_stopped.connect(on_session_stopped)
            recognizer.canceled.connect(on_canceled)

            recognizer.start_continuous_recognition()
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, done_event.wait),
                timeout=600,
            )
            recognizer.stop_continuous_recognition()

            full_text = " ".join(r["text"] for r in all_results)
            segments = [
                {
                    "start": r["offset"],
                    "end": r["offset"] + r["duration"],
                    "text": r["text"],
                }
                for r in all_results
            ]

            total_duration = (
                segments[-1]["end"] if segments else 0.0
            )

            return {
                "filename": params.path,
                "duration_seconds": round(total_duration, 2),
                "language": params.language,
                "text": full_text,
                "segments": segments,
            }
        finally:
            os.unlink(tmp_path)

    except Exception as exc:
        logger.exception(
            "transcribe_audio failed for %s/%s", params.container, params.path
        )
        return {"error": str(exc), "filename": params.path}
