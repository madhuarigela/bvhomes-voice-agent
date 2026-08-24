"""Conversation transcript rendering and Gemini-powered call summaries."""

from __future__ import annotations

import json
import logging
from typing import Any

from livekit.agents import llm

logger = logging.getLogger("bvhomes-agent.conversation")

_SUMMARY_INSTRUCTIONS = """Summarize this completed BVHomes Furniture voice call.
Return ONLY valid JSON with these string fields: summary, topics_discussed,
products_discussed, budget, requirements, lead_status, follow_up_action.
Use comma-separated values for topics_discussed and products_discussed. lead_status
must be one of: new, qualified, callback_requested, closed. Never invent facts;
use empty strings for details not mentioned."""


def transcript_from_history(history: llm.ChatContext) -> str:
    """Render customer/assistant messages only; excludes system prompts and tool payloads."""
    lines: list[str] = []
    for message in history.messages():
        if message.role not in ("user", "assistant"):
            continue
        parts: list[str] = []
        for item in message.content:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif getattr(item, "transcript", None):
                parts.append(item.transcript.strip())
        if parts:
            speaker = "Customer" if message.role == "user" else "BVHomes Agent"
            lines.append(f"{speaker}: {' '.join(parts)}")
    return "\n".join(lines)


async def summarize_conversation(model: llm.LLM, transcript: str) -> dict[str, str]:
    """Ask the configured Gemini model for structured call metadata.

    Raises are deliberately left to the caller, which can persist the transcript
    even if the optional summarization request fails.
    """
    empty = {
        "summary": "",
        "topics_discussed": "",
        "products_discussed": "",
        "budget": "",
        "requirements": "",
        "lead_status": "new",
        "follow_up_action": "",
    }
    if not transcript.strip():
        return empty

    context = llm.ChatContext.empty()
    context.add_message(role="system", content=_SUMMARY_INSTRUCTIONS)
    context.add_message(role="user", content=transcript)
    response = await model.chat(chat_ctx=context).collect()
    raw = response.chat_message.text_content if response.chat_message else ""
    if not raw:
        return empty
    try:
        parsed: dict[str, Any] = json.loads(raw.strip().removeprefix("```json").removesuffix("```"))
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Gemini returned a non-JSON conversation summary")
        return {**empty, "summary": raw.strip()}

    result = {key: str(parsed.get(key, default) or default) for key, default in empty.items()}
    if result["lead_status"] not in {"new", "qualified", "callback_requested", "closed"}:
        result["lead_status"] = "new"
    return result
