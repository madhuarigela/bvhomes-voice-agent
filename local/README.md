# BV Homes — Open-Source Local Stack

This branch is the local-first rebuild of BV Homes. The production `main` branch is intentionally untouched.

## Goal

Remove hosted AI dependencies from the BV Homes intelligence and speech stack:

- LLM: Ollama (OpenAI-compatible local API)
- STT: faster-whisper, running locally
- TTS: Piper, running locally
- Data: SQLite/PostgreSQL, no SaaS requirement
- Realtime transport: self-hosted LiveKit Server + Redis
- Agent logic/tools: the existing BV Homes Python code
- No Gemini API
- No Sarvam API
- No LiveKit Cloud inference

LiveKit itself is open source and can be self-hosted. The official documentation explicitly supports connecting agents to a self-hosted LiveKit server and using model plugins instead of LiveKit Inference.

## Architecture

```
Browser microphone
      |
      v
Self-hosted LiveKit Server
      |
      v
BV Homes Local Agent
      |
      +--> Local STT (faster-whisper)
      |
      +--> Ollama LLM
      |       |
      |       +--> get_product_price
      |       +--> save_lead
      |       +--> request_executive_callback
      |
      +--> Local SQLite/PostgreSQL
      |
      +--> Local Piper TTS
      |
      v
Browser speaker
```

## Important

The first implementation deliberately builds the local model services and agent core before replacing the realtime LiveKit nodes. This lets us benchmark each model independently and avoids breaking the existing production branch.

## Models

Default LLM:

```
BVHOMES_OLLAMA_MODEL=qwen3.6:latest
```

Change it to the exact model tag already installed on your machine.

Default STT:

```
BVHOMES_STT_MODEL=small
```

For better Telugu quality, test `large-v3` or an IndicConformer build once the local hardware benchmark is known.

TTS uses Piper. Set `BVHOMES_PIPER_VOICE` to a downloaded Telugu voice model.

## Start

1. Start Ollama and make sure the selected model is installed.
2. Start the local speech services:

```
python -m local.speech_server
```

3. Start the local text agent:

```
python -m local.agent
```

4. Start self-hosted LiveKit + Redis:

```
docker compose -f local/livekit.compose.yml up -d
```

The remaining work is the realtime adapter that connects LiveKit audio frames to the local STT/TTS services. The services are intentionally isolated so that adapter work does not affect the production branch.

## Zero-cost boundary

Local development and model inference can have zero API cost. A public Internet deployment still requires compute, bandwidth, and—if we later support ordinary phone numbers—telephony/SIP carrier service. The browser/WebRTC version can remain entirely self-hosted.
