from __future__ import annotations

import os
from pathlib import Path


MODEL_NAME = os.getenv("WHISPER_MODEL", "small")
DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

_model = None


def get_model():
    global _model
    if _model is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - runtime protection
            raise RuntimeError(
                "faster-whisper is not installed. Install dependencies before using voice features."
            ) from exc

        _model = WhisperModel(
            MODEL_NAME,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )
    return _model


def transcribe_file(path: str) -> str:
    audio_path = Path(path)
    if not audio_path.exists():
        raise RuntimeError("Audio file was not downloaded correctly.")

    model = get_model()
    segments, _ = model.transcribe(audio_path.as_posix())
    text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    return text.strip()
