# BVHomes Telephony Setup (SIP / Phone Number)

The agent itself (`agent/main.py`) has **no telephony code**. A phone call
becomes a LiveKit room participant via LiveKit's SIP service — the same
agent that works in local console mode picks up the call automatically once
it's registered as a worker. This doc only covers the SIP/phone-number side.

## Prerequisites

- A LiveKit Cloud project (or self-hosted LiveKit + `livekit-sip` service)
- A SIP trunking provider account with an Indian number, e.g. **Exotel**,
  **Twilio Elastic SIP Trunking**, **Telnyx**, or **Plivo**. Pick one that
  supports Indian DID numbers and SIP trunking specifically (not every
  provider does IN numbers the same way — verify before buying).

  **Cost tip:** for minimum running cost, a **direct carrier SIP trunk**
  (Airtel Business, Jio, or BSNL) is typically cheaper than managed CPaaS
  platforms like Exotel/Ozonetel, which bundle a monthly SaaS/seat fee for
  IVR/dialer features you don't need — LiveKit's agent already provides
  that layer. Direct carrier trunks run roughly ₹500/month rental plus
  ₹0.30–0.90/min, versus CPaaS platforms' monthly per-agent pricing on top
  of usage. Twilio/Telnyx are solid if you want easier self-serve signup
  and don't mind paying a bit more for India-only routing.
- The `lk` CLI installed and logged into your LiveKit project:
  ```
  lk cloud auth
  ```

## Step 1 — Buy a number + create a SIP trunk with your provider

Follow your provider's SIP trunking docs. You'll end up with:
- A phone number (E.164 format, e.g. `+9179XXXXXXXX`)
- A SIP domain/address for that trunk
- Auth credentials (username/password) if using authenticated trunking

## Step 2 — Create the LiveKit inbound trunk

Edit `inbound-trunk.json` in this folder: replace `+91XXXXXXXXXX` with your
real number. Then:

```
lk sip inbound create --request telephony/inbound-trunk.json
```

Note the returned `SIPTrunkID` — you need it for the dispatch rule.

## Step 3 — Create the dispatch rule

Edit `dispatch-rule.json`: replace `YOUR_INBOUND_TRUNK_ID` with the ID from
Step 2. Then:

```
lk sip dispatch create --request telephony/dispatch-rule.json
```

This tells LiveKit: "when a call comes in on this trunk, create a new room
per caller and let any registered agent worker join it." Since the BVHomes
agent worker (`uv run -m agent.main start`) is always listening for jobs, it
will automatically join.

## Step 4 — Point your SIP provider at LiveKit

In your SIP provider's dashboard, set the SIP trunk destination to your
LiveKit project's SIP URI (found in LiveKit Cloud dashboard → Settings →
Project, labeled "SIP URI", looks like `<subdomain>.sip.livekit.cloud`).

## Step 5 — Test

Call your BVHomes number from a real phone. You should hear Priya's Telugu
greeting. If the call connects but there's silence, check:
- The agent worker is running (`uv run -m agent.main start`) and its
  `LIVEKIT_URL` / API key / secret match the same project as the trunk.
- The dispatch rule's `trunk_ids` matches the actual inbound trunk ID.
- LiveKit Cloud dashboard → Telephony → Logs, for call-level errors.

## Outbound calls (optional, for callback campaigns later)

Edit `outbound-trunk.json` with your provider's trunk address + auth, then:

```
lk sip outbound create --request telephony/outbound-trunk.json
```

To place an outbound call into a room (e.g. from an automation triggered off
the `leads` table for a callback):

```
lk sip participant create \
  --room "bvhomes-outbound-<id>" \
  --trunk "<OUTBOUND_TRUNK_ID>" \
  --call "+91XXXXXXXXXX" \
  --identity "outbound-caller"
```

This is a manual/scriptable building block — an actual outbound calling
campaign scheduler is not built here; it's a reasonable Phase 3 addition once
inbound is proven out.

## Costs to expect

- LiveKit SIP: ~$0.003–$0.004/min (LiveKit side)
- Your SIP provider: carrier passthrough, varies by provider/route for
  Indian PSTN termination — get a quote for IN inbound + outbound rates
  specifically, international per-minute lists often don't apply cleanly.
- See main README.md cost section for the full per-minute stack estimate.
