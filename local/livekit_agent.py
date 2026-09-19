from __future__ import annotations

import asyncio
import io
import os
import subprocess
import tempfile
import time
import wave
from collections.abc import AsyncIterable

import numpy as np
from livekit import agents, rtc
from livekit.agents import Agent, AgentServer, AgentSession, ModelSettings, cli, llm, room_io, stt
from livekit.plugins import openai as openai_plugin

from agent.prompts import build_system_instructions
from agent.storage import LeadStore
from agent.tools import BVHomesTools

LIVEKIT_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")
OLLAMA_URL = os.getenv("BVHOMES_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
OLLAMA_MODEL = os.getenv("BVHOMES_OLLAMA_MODEL", "qwen3.6:latest")
PIPER_MODEL = os.getenv("BVHOMES_PIPER_VOICE", "")

SILENCE_RMS = float(os.getenv("BVHOMES_VAD_RMS", "450"))
SILENCE_SECONDS = float(os.getenv("BVHOMES_VAD_SILENCE", "0.65"))
MAX_UTTERANCE_SECONDS = float(os.getenv("BVHOMES_MAX_UTTERANCE", "20"))


def rms(frame: rtc.AudioFrame) -> float:
    data = np.frombuffer(frame.data, dtype=np.int16)
    if data.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(data.astype(np.float32)))))


def wav_bytes(frames: list[rtc.AudioFrame]) -> bytes:
    merged = rtc.combine_audio_frames(frames)
    return merged.to_wav_bytes()


async def local_stt_node(
    audio: AsyncIterable[rtc.AudioFrame],
) -> AsyncIterable[stt.SpeechEvent]:
    frames: list[rtc.AudioFrame] = []
    speaking = False
    silence = 0.0
    started_at = 0.0
    sample_rate = 48000

    async def transcribe(current: list[rtc.AudioFrame]):
        if not current:
            return ""
        data = wav_bytes(current)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(data)
            path = tmp.name
        try:
            from faster_whisper import WhisperModel

            # Loaded once per process after the first turn.
            if not hasattr(local_stt_node, "_model"):
                local_stt_node._model = WhisperModel(
                    os.getenv("BVHOMES_STT_MODEL", "small"),
                    device=os.getenv("BVHOMES_STT_DEVICE", "cpu"),
                    compute_type=os.getenv("BVHOMES_STT_COMPUTE_TYPE", "int8"),
                )
            model = local_stt_node._model
            segments, info = await asyncio.to_thread(
                model.transcribe,
                path,
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=False,
                task="transcribe",
            )
            text = " ".join(s.text.strip() for s in segments).strip()
            return text
        finally:
            os.unlink(path)

    async def finish():
        nonlocal frames, speaking, silence, started_at
        if not speaking or not frames:
            frames = []
            speaking = False
            silence = 0.0
            return
        text = await transcribe(frames)
        end_time = time.time()
        if text:
            yield stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[
                    stt.SpeechData(
                        language="te",
                        text=text,
                        start_time=started_at,
                        end_time=end_time,
                        confidence=1.0,
                    )
                ],
                speech_start_time=started_at,
                speech_end_time=end_time,
            )
        yield stt.SpeechEvent(
            type=stt.SpeechEventType.END_OF_SPEECH,
            speech_end_time=end_time,
        )
        frames = []
        speaking = False
        silence = 0.0
        started_at = 0.0

    async for frame in audio:
        sample_rate = frame.sample_rate
        level = rms(frame)
        duration = frame.duration

        if level >= SILENCE_RMS:
            if not speaking:
                speaking = True
                started_at = time.time()
                yield stt.SpeechEvent(type=stt.SpeechEventType.START_OF_SPEECH)
            frames.append(frame)
            silence = 0.0
        elif speaking:
            frames.append(frame)
            silence += duration
            if silence >= SILENCE_SECONDS:
                async for event in finish():
                    yield event

        if speaking and started_at and time.time() - started_at >= MAX_UTTERANCE_SECONDS:
            async for event in finish():
                yield event

    async for event in finish():
        yield event


async def local_tts_node(
    text: AsyncIterable[str],
    model_settings: ModelSettings,
) -> AsyncIterable[rtc.AudioFrame]:
    if not PIPER_MODEL:
        raise RuntimeError(
            "BVHOMES_PIPER_VOICE is not configured. "
            "Set it to a local Piper Telugu .onnx voice."
        )

    chunks: list[str] = []
    async for chunk in text:
        if chunk:
            chunks.append(chunk)
    spoken = "".join(chunks).strip()
    if not spoken:
        return

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "reply.wav")
        proc = await asyncio.create_subprocess_exec(
            "python",
            "-m",
            "piper",
            "--model",
            PIPER_MODEL,
            "--output_file",
            out,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate(spoken.encode("utf-8"))
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="replace"))

        with wave.open(out, "rb") as wav:
            sample_rate = wav.getframerate()
            channels = wav.getnchannels()
            pcm = wav.readframes(wav.getnframes())

        frame_samples = max(1, sample_rate // 50)  # 20ms
        bytes_per_sample = 2 * channels
        step = frame_samples * bytes_per_sample

        for offset in range(0, len(pcm), step):
            chunk = pcm[offset : offset + step]
            samples = len(chunk) // bytes_per_sample
            if samples:
                yield rtc.AudioFrame(
                    data=chunk,
                    sample_rate=sample_rate,
                    num_channels=channels,
                    samples_per_channel=samples,
                )


class BVHomesLocalVoiceAgent(Agent):
    async def stt_node(
        self,
        audio: AsyncIterable[rtc.AudioFrame],
        model_settings: ModelSettings,
    ):
        async for event in local_stt_node(audio):
            yield event

    async def tts_node(
        self,
        text: AsyncIterable[str],
        model_settings: ModelSettings,
    ):
        async for frame in local_tts_node(text, model_settings):
            yield frame

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions=(
                "Greet the customer warmly in Telugu as Priya from BVHomes Furniture. "
                "Keep the greeting short."
            )
        )


server = AgentServer()


@server.rtc_session(agent_name="bvhomes-local")
async def entrypoint(ctx: agents.JobContext):
    store = LeadStore(os.getenv("BVHOMES_DB_PATH", "local/data/bvhomes_local.db"))
    await store.init()

    tools = BVHomesTools(store=store, room_name=ctx.room.name)

    local_llm = openai_plugin.LLM(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_URL,
        api_key="ollama",
    )

    session = AgentSession(
        llm=local_llm,
        stt=None,
        tts=None,
        vad=None,
        turn_detection="stt",
        max_endpointing_delay=1.0,
        max_tool_steps=4,
    )

    await session.start(
        agent=BVHomesLocalVoiceAgent(
            instructions=build_system_instructions(),
            tools=[
                tools.get_product_price,
                tools.save_lead,
                tools.request_executive_callback,
            ],
        ),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(),
        ),
    )


if __name__ == "__main__":
    cli.run_app(server)
