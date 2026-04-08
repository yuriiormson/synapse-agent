from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

from app.config import SETTINGS


logger = logging.getLogger(__name__)
MAX_AUDIO_DURATION_SECONDS = 300
VALID_WHISPER_MODELS = {
    "tiny",
    "tiny.en",
    "base",
    "base.en",
    "small",
    "small.en",
    "medium",
    "medium.en",
    "large-v1",
    "large-v2",
    "large-v3",
    "distil-small.en",
    "distil-medium.en",
    "distil-large-v2",
    "distil-large-v3",
    "turbo",
}


@dataclass(slots=True)
class TranscriptionResult:
    text: str
    language: str | None = None
    duration: float | None = None


_MODEL = None
_MODEL_NAME = None


def _validated_model_name(raw_model: str) -> str:
    candidate = (raw_model or "").strip().lower()
    if candidate in VALID_WHISPER_MODELS:
        return candidate
    logger.error("Unsupported Whisper model '%s'. Falling back to base.", raw_model)
    return "base"


def _get_model():
    global _MODEL, _MODEL_NAME
    model_name = _validated_model_name(SETTINGS.whisper_model)
    if _MODEL is None or _MODEL_NAME != model_name:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - runtime protection
            raise RuntimeError(
                "faster-whisper is not installed. Install dependencies before using voice features."
            ) from exc

        try:
            _MODEL = WhisperModel(
                model_name,
                device=SETTINGS.whisper_device,
                compute_type=SETTINGS.whisper_compute_type,
            )
            _MODEL_NAME = model_name
        except Exception as exc:  # pragma: no cover - runtime protection
            if model_name != "base":
                logger.error(
                    "Failed to load Whisper model '%s'. Falling back to base.",
                    model_name,
                    exc_info=True,
                )
                try:
                    _MODEL = WhisperModel(
                        "base",
                        device=SETTINGS.whisper_device,
                        compute_type=SETTINGS.whisper_compute_type,
                    )
                    _MODEL_NAME = "base"
                except Exception as fallback_exc:  # pragma: no cover - runtime protection
                    logger.error("Failed to load fallback Whisper model 'base'.", exc_info=True)
                    raise RuntimeError("Could not load the local speech-to-text model.") from fallback_exc
            else:
                logger.error("Failed to load Whisper model '%s'.", model_name, exc_info=True)
                raise RuntimeError("Could not load the local speech-to-text model.") from exc
    return _MODEL


def transcribe_audio(audio_path: str | Path) -> TranscriptionResult:
    path = Path(audio_path)
    if not path.exists():
        raise RuntimeError("Audio file was not downloaded correctly.")
    model = _get_model()
    logger.info("Starting voice transcription for %s", path.name)
    try:
        segments, info = model.transcribe(
            path.as_posix(),
            beam_size=1,
            vad_filter=True,
        )
    except Exception as exc:  # pragma: no cover - runtime protection
        logger.error("Voice decoding failed: %s", exc, exc_info=True)
        raise RuntimeError("Could not decode audio.") from exc

    duration = getattr(info, "duration", None)
    if duration and duration > MAX_AUDIO_DURATION_SECONDS:
        logger.warning("Rejected long audio (%.2fs) for %s", duration, path.name)
        raise RuntimeError("Audio is too long. Please keep it under 5 minutes.")

    parts: list[str] = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            parts.append(text)

    transcript = " ".join(parts).strip()
    if not transcript:
        logger.warning("Voice transcription produced an empty transcript for %s", path.name)
        raise RuntimeError("Could not understand audio.")

    logger.info("Voice transcription complete for %s", path.name)

    return TranscriptionResult(
        text=transcript,
        language=getattr(info, "language", None),
        duration=duration,
    )
