# BVHomes Phone Calling

This project now supports both inbound and outbound phone calls through LiveKit SIP.

## Architecture

Phone ↔ SIP provider ↔ LiveKit SIP ↔ \`bvhomes-sales-agent\` ↔ Sarvam STT/TTS + Gemini/Ollama.

The uploaded roadmap's Asterisk/Vosk/Coqui stack is not copied into this repository because the existing agent already uses LiveKit SIP, Sarvam Saaras/Bulbul, and Gemini/Ollama. Replacing those components would discard working BVHomes functionality.

## Inbound calls

1. Create an inbound SIP trunk.
2. Put its ID into \`telephony/dispatch-rule.json\`.
3. Create the dispatch rule.
4. Run/deploy the agent worker.
5. Call the BVHomes number.

The dispatch rule explicitly sends each call to \`bvhomes-sales-agent\`.

## Outbound calls

Create an outbound SIP trunk in LiveKit and put its ID in:

\`\`\`env
SIP_OUTBOUND_TRUNK_ID=ST_xxxxxxxxx
\`\`\`

Then run:

\`\`\`uv run python scripts/place_call.py +919876543210\`\`\`

Optional context:

\`\`\`uv run python scripts/place_call.py +919876543210 --reason "Follow up about the L-type sofa"\`\`\`

The script:

1. Creates a unique LiveKit room.
2. Explicitly dispatches \`bvhomes-sales-agent\`.
3. Creates a SIP participant using the outbound trunk.
4. Waits for the call to be answered.
5. Connects the phone participant to the AI agent.
6. The agent greets the customer and continues the normal BVHomes sales conversation.
7. Existing lead and conversation persistence remains active.

## Credentials

Never commit real SIP passwords, API secrets, or phone numbers to GitHub. Keep them in \`.env\` or LiveKit Cloud secrets.

## What you still need outside GitHub

Code cannot create a real PSTN number by itself. You still need:

- A LiveKit Cloud project.
- Sarvam API access.
- An outbound SIP trunk with a provider.
- A phone number permitted for the required calling route.
- The returned LiveKit outbound trunk ID.

LiveKit's current outbound-call flow is: create an agent dispatch, create a SIP participant, and connect that participant to the dispatched agent room. citeturn2search2turn2search3
