from __future__ import annotations

import io
import os
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import Response
from faster_whisper import WhisperModel

app = FastAPI(title="BV Homes Local Speech Services")

STT_MODEL = os.getenv("BVHOMES_STT_MODEL", "small")
STT_DEVICE = os.getenv("BVHOMES_STT_DEVICE", "cpu")
STT_COMPUTE = os.getenv("BVHOMES_STT_COMPUTE_TYPE", "int8")
PIPER_VOICE = os.getenv("BVHOMES_PIPER_VOICE", "")

_whisper: WhisperModel | None = None


def whisper() -> WhisperModel:
    global _whisper
    if _whisper is None:
        _whisper = WhisperModel(
            STT_MODEL,
            device=STT_DEVICE,
            compute_type=STT_COMPUTE,
        )
    return _whisper


@app.get("/health")
async def health():
    return {
        "ok": True,
        "stt_model": STT_MODEL,
        "stt_device": STT_DEVICE,
        "piper_voice_configured": bool(PIPER_VOICE),
    }


@app.post("/stt")
async def stt(file: UploadFile = File(...)):
    data = await file.read()
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        path = tmp.name

    try:
        segments, info = whisper().transcribe(
            path,
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
            task="transcribe",
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return {
            "text": text,
            "language": info.language,
            "language_probability": info.language_probability,
        }
    finally:
        Path(path).unlink(missing_ok=True)


@app.post("/tts")
async def tts(payload: dict):
    text = str(payload.get("text", "")).strip()
    voice = str(payload.get("voice") or PIPER_VOICE).strip()

    if not text:
        return Response(status_code=400, content="text is required")
    if not voice:
        return Response(
            status_code=400,
            content="Set BVHOMES_PIPER_VOICE to a downloaded Piper Telugu voice model.",
        )

    # Piper writes WAV to stdout. The voice model path is supplied by the
    # caller/environment, so no hosted TTS service is involved.
    proc = subprocess.run(
        ["python", "-m", "piper", "--model", voice, "--output-raw"],
        input=text.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if proc.returncode != 0:
        return Response(
            status_code=500,
            content=proc.stderr.decode("utf-8", errors="replace"),
        )

    # output-raw is PCM. Ask Piper again for a WAV container so clients can
    # consume it without guessing the sample format.
    wav_proc = subprocess.run(
        ["python", "-m", "piper", "--model", voice, "--output_file", "-"],
        input=text.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if wav_proc.returncode != 0:
        return Response(
            status_code=500,
            content=wav_proc.stderr.decode("utf-8", errors="replace"),
        )

    return Response(content=wav_proc.stdout, media_type="audio/wav")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("local.speech_server:app", host="127.0.0.1", port=5000, reload=False)
