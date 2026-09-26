"""
BVHomes Furniture - Multilingual Voice Sales Agent

Local mic/speaker testing:
    uv run -m agent.main console

Local LiveKit room testing:
    uv run -m agent.main dev

Production worker:
    uv run -m agent.main start
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    MetricsCollectedEvent,
    cli,
    inference,
    room_io,
)
from livekit.plugins import sarvam

from agent.config import load_config
from agent.conversation import summarize_conversation, transcript_from_history
from agent.prompts import build_system_instructions
from agent.storage import ConversationRecord, LeadStore
from agent.tools import BVHomesTools

logger = logging.getLogger("bvhomes-agent")

config = load_config()

logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

lead_store = LeadStore(config.database_url or config.db_path)


def build_llm():
    """Choose the LLM backend."""
    if config.llm_provider == "ollama":
        logger.warning(
            "Using Ollama model %s at %s",
            config.ollama_model,
            config.ollama_base_url,
        )
        from livekit.plugins import openai as openai_plugin

        return openai_plugin.LLM(
            model=config.ollama_model,
            base_url=config.ollama_base_url,
            api_key="ollama",
        )

    return inference.LLM("google/gemini-2.5-flash")


class BVHomesAgent(Agent):
    def __init__(self, tools: BVHomesTools, outbound: bool = False) -> None:
        super().__init__(
            instructions=build_system_instructions(),
            tools=[
                tools.get_product_price,
                tools.save_lead,
                tools.request_executive_callback,
            ],
        )
        self.outbound = outbound

    async def on_enter(self) -> None:
        if self.outbound:
            self.session.generate_reply(
                instructions=(
                    "This is an outbound BVHomes customer call. Greet the person "
                    "briefly as Priya from BVHomes Furniture, explain why you are "
                    "calling if the context is available, then ask if this is a "
                    "good time to speak. Do not assume they are the customer or "
                    "that they requested a callback."
                )
            )
            return

        self.session.generate_reply(
            instructions=(
                "Greet the customer warmly in Telugu as Priya from BVHomes "
                "Furniture, and ask how you can help them today."
            )
        )


server = AgentServer()


@server.rtc_session(agent_name="bvhomes-sales-agent")
async def entrypoint(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}
    logger.info("Agent job starting for room=%s", ctx.room.name)

    try:
        await lead_store.init()
    except Exception:
        logger.exception(
            "Lead store init failed - leads will not be saved this session"
        )

    tools = BVHomesTools(store=lead_store, room_name=ctx.room.name)
    session_llm = build_llm()
    session_started_at = datetime.now(UTC)

    outbound = bool(ctx.job.metadata and '"outbound"' in ctx.job.metadata.lower())

    session = AgentSession(
        stt=sarvam.STT(
            model="saaras:v3",
            language="unknown",
            mode="transcribe",
            flush_signal=True,
        ),
        llm=session_llm,
        tts=sarvam.TTS(
            model="bulbul:v3",
            target_language_code="te-IN",
            speaker=config.tts_speaker,
        ),
        turn_detection="stt",
        min_endpointing_delay=0.07,
    )

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent) -> None:
        if ev.metrics.type == "stt_metrics":
            return
        try:
            logger.info("metrics: %s", ev.metrics)
        except Exception:
            logger.exception("Failed to log metrics")

    async def persist_completed_conversation():
        try:
            logger.info("Usage for room=%s: %s", ctx.room.name, session.usage)
        except Exception:
            logger.exception("Failed to log usage summary")

        try:
            ended_at = datetime.now(UTC)
            transcript = transcript_from_history(session.history)
            summary = await summarize_conversation(session_llm, transcript)
            lead = await lead_store.latest_lead_for_room(ctx.room.name) or {}
            await lead_store.save_conversation(
                ConversationRecord(
                    room_name=ctx.room.name,
                    started_at=session_started_at.isoformat(),
                    ended_at=ended_at.isoformat(),
                    duration_seconds=max(
                        0, int((ended_at - session_started_at).total_seconds())
                    ),
                    transcript=transcript,
                    ai_summary=summary["summary"],
                    topics_discussed=summary["topics_discussed"],
                    products_discussed=summary["products_discussed"],
                    budget=summary["budget"] or str(lead.get("budget", "")),
                    requirements=summary["requirements"]
                    or str(lead.get("furniture_requirement", "")),
                    customer_name=str(lead.get("name", "")),
                    customer_phone=str(lead.get("phone_number", "")),
                    lead_status=summary["lead_status"],
                    follow_up_action=summary["follow_up_action"]
                    or str(lead.get("callback_reason", "")),
                )
            )
        except Exception:
            logger.exception(
                "Failed to persist completed conversation for room=%s",
                ctx.room.name,
            )

    ctx.add_shutdown_callback(persist_completed_conversation)

    try:
        await session.start(
            agent=BVHomesAgent(tools=tools, outbound=outbound),
            room=ctx.room,
            room_options=room_io.RoomOptions(
                audio_input=room_io.AudioInputOptions(),
            ),
        )
    except Exception:
        logger.exception("Session failed for room=%s", ctx.room.name)
        raise


if __name__ == "__main__":
    cli.run_app(server)
