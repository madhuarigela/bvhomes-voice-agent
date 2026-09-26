"""Place an outbound BVHomes AI call through LiveKit SIP.

Usage:
    uv run python scripts/place_call.py +919876543210

Required environment variables:
    LIVEKIT_URL
    LIVEKIT_API_KEY
    LIVEKIT_API_SECRET
    SIP_OUTBOUND_TRUNK_ID

The worker must be deployed/running as the \`bvhomes-sales-agent\` agent.
The phone number must be in E.164 format.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import uuid

from dotenv import load_dotenv
from livekit import api

PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")
AGENT_NAME = "bvhomes-sales-agent"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call a phone number with BVHomes AI")
    parser.add_argument("phone_number", help="Destination number in E.164 format, e.g. +919876543210")
    parser.add_argument(
        "--reason",
        default="BVHomes follow-up call",
        help="Context shown to the agent for this outbound call",
    )
    return parser.parse_args()


async def place_call(phone_number: str, reason: str) -> None:
    if not PHONE_RE.fullmatch(phone_number):
        raise SystemExit(
            "Invalid phone number. Use E.164 format, for example +919876543210."
        )

    trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")
    if not trunk_id:
        raise SystemExit("Missing SIP_OUTBOUND_TRUNK_ID.")

    room_name = f"bvhomes-outbound-{uuid.uuid4().hex[:12]}"
    metadata = (
        '{"outbound": true, '
        f'"phone_number": "{phone_number}", '
        f'"reason": "{reason.replace(chr(34), chr(39))}"' 
        "}"
    )

    async with api.LiveKitAPI() as lkapi:
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=room_name,
                metadata=metadata,
            )
        )

        try:
            participant = await lkapi.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    sip_trunk_id=trunk_id,
                    sip_call_to=phone_number,
                    room_name=room_name,
                    participant_identity=f"sip-{phone_number.lstrip('+')}",
                    participant_name="BVHomes Customer",
                    wait_until_answered=True,
                    play_dialtone=True,
                )
            )
        except api.SipCallError as exc:
            raise SystemExit(
                f"Call failed: SIP {exc.sip_status_code} {exc.sip_status}"
            ) from exc

        print(
            f"Call connected: {phone_number} "
            f"(participant={participant.participant_identity}, room={room_name})"
        )


def main() -> None:
    load_dotenv()
    args = parse_args()
    asyncio.run(place_call(args.phone_number, args.reason))


if __name__ == "__main__":
    main()
