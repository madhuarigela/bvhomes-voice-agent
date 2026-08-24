# BVHomes Furniture — Multilingual Voice Sales Agent

A LiveKit-based voice agent for BVHomes Furniture (Visakhapatnam) that speaks
Telugu-first with natural English/Hindi code-switching, answers questions
from a fixed product catalog, and captures customer leads for human
follow-up. Built to run identically in local mic/speaker testing and behind
a real phone number.

```
Customer phone call
   → LiveKit SIP
   → Sarvam Saaras v3 (STT)
   → BVHomes Agent (Gemini 2.5 Flash)
   → Sarvam Bulbul v3 (TTS)
   → Customer
```

## Why this stack

- **STT/TTS: Sarvam AI (Saaras v3 / Bulbul v3)** — the only evaluated
  provider purpose-built for Telugu-English code-switching, not a bolt-on.
  Deepgram/Google/Azure all support Telugu as one-of-many languages but none
  natively handle Telugu-English mixing the way Sarvam does.
- **LLM: Gemini 2.5 Flash** via LiveKit Inference — cheap, low-latency,
  reliable function/tool-calling for the lead-capture tools below.
- **Storage: SQLite (aiosqlite)** — zero extra infrastructure for a single
  small business; swap-in point is isolated to `agent/storage.py` if you
  later want Postgres/CRM/Airtable.
- **Telephony: LiveKit SIP** — the agent has no telephony-specific code at
  all. A phone call and a browser/app call look identical to `agent/main.py`.

## Cost optimization decisions

Every layer was re-evaluated for minimum practical cost. Summary — what's
free, what costs money, and why:

| Layer | Choice | Cost | Why not free/local |
|---|---|---|---|
| **STT** | Sarvam Saaras v3 | Paid (~Rs 1.5/min) | No free/local Telugu-English code-switching STT exists at usable quality — Whisper and other local models are weak specifically on Telugu and don't handle code-switching natively. This is the one layer where "free" would directly break the core requirement. |
| **TTS** | Sarvam Bulbul v3 | Paid (~Rs 30/10K chars) | Same reasoning — no free/local Telugu TTS approaches the naturalness needed for a sales call. Coqui/Piper-style open TTS exist but Telugu voice quality is far behind. |
| **LLM** | **Gemini 2.5 Flash (default)** | Paid, but tiny (~$0.001-0.005/min) | See "LLM: why not local by default" below. |
| **LLM (optional)** | Ollama, local model | **$0 marginal cost** | Opt-in via `BVHOMES_LLM_PROVIDER=ollama`. Off by default — see below. |
| **Database** | SQLite (`aiosqlite`) | **Free** | Already the cheapest correct choice for this call volume — no change needed. |
| **Hosting** | Any small VM/container host + LiveKit Cloud Build tier | **Free to start** | LiveKit Cloud's free Build tier (1,000 agent-minutes/month) covers early-stage volume entirely. Self-hosting LiveKit's SIP/media server is possible (Apache 2.0) but adds real ops burden (Redis, public IP, TURN/media ports) that isn't worth it below serious call volume — revisit only if you exceed the free tier regularly. |
| **Telephony/SIP carrier** | Direct carrier SIP trunk (Airtel Business / Jio / BSNL) | **Cheapest reliable option** (~Rs 500/month + Rs 0.30-0.90/min) | Managed CPaaS platforms (Exotel, Ozonetel) charge a monthly SaaS/seat fee on top of carrier rates for IVR/dialer features you don't need — LiveKit's agent already provides that layer. A direct carrier SIP trunk skips that markup. Twilio/Telnyx work too but usually cost more for India-only routing than a direct desi carrier trunk. |

### Actually test Ollama yourself: `scripts/eval_llm_telugu.py`

The engineering call above (Gemini default, Ollama opt-in) is based on
published research about Telugu being low-resource for open models - not on
a live test, because **this build environment has no network access to
ollama.com or any model registry**, confirmed directly (`curl` to
`ollama.com` returns `403 host_not_allowed` here). So instead of asserting
a conclusion that couldn't be personally verified, there's a runnable
harness:

```
ollama pull llama3.3:8b      # or any model you want to evaluate
ollama serve                  # separate terminal
uv sync --extra ollama
uv run python -m scripts.eval_llm_telugu
```

It sends the same 5 BVHomes-realistic prompts (Telugu price question, pure
Telugu with unknown measurements, Telugu-English code-switch on a custom
item, Hindi, English) through both Gemini and your local Ollama model using
the exact same system prompt the real agent uses, and prints both
side-by-side so you (or a Telugu speaker on your team) can judge fluency
and code-switch quality directly. **This script itself was run in this
environment and confirmed structurally correct** - it builds both LLM
clients against the real `livekit-agents`/`livekit-plugins-openai`
packages, and handles a missing/unreachable provider gracefully (tested:
Gemini correctly skips without a real key, Ollama fails cleanly with a
clear connection error). Only the actual model *responses* are untested,
since that requires a live Ollama server this sandbox can't reach.


### LLM: why not local by default

Ollama (or any local runtime) is genuinely free to run — zero marginal
cost, keeps data on your own machine. It was seriously considered as the
default. It isn't, for one specific reason: **Telugu is a low-resource
language for every open local model available today.** Published evals
consistently show open models (Llama, Qwen, Gemma, Mistral) losing significant
quality specifically on Telugu even where they perform fine on English,
Hindi, or higher-resource languages — and BVHomes' core requirement is
natural Telugu-English code-switching, which is exactly where quality drops
hit hardest. Gemini 2.5 Flash costs a fraction of a cent per call and gives
reliable Telugu/Hindi/English generation plus dependable tool-calling for
the lead-capture tools — at BVHomes' expected call volume this is close to
a rounding error, not a meaningful expense.

**Ollama is fully wired up and available** — set `BVHOMES_LLM_PROVIDER=ollama`
and `uv sync --extra ollama`, run `ollama serve` locally with a model like
`llama3.3:8b` pulled, and the agent routes to it automatically via Ollama's
OpenAI-compatible API. `agent/main.py` logs a clear warning when this path is
active, because **its Telugu/code-switching quality is unverified** — the
right way to use it is: test it yourself with real Telugu conversation
against your hardware, and only rely on it in production if it holds up. A
reasonable middle ground if you want to explore this further: keep Gemini as
the default and only route to Ollama for low-stakes/English-heavy turns, or
revisit this once a stronger open Telugu-specific model (e.g. an
Indic-tuned model such as Krutrim or Navarasa, evaluated in recent
multilingual-hallucination research) is available on Ollama with
established quality.

### Deterministic pricing (no more LLM-invented prices)

Previously, prices lived only in the system prompt as text, which an LLM
could in principle misstate. This is now hardened: `agent/tools.py` exposes
a `get_product_price` tool that does an exact Python dictionary lookup
against `agent/business_data.py` — the LLM has no code path that produces a
price that isn't in `PRODUCTS`. The system prompt (`prompts.py`) explicitly
instructs the model to call this tool before stating any price, every time,
and never to read a price from the prompt text directly. Tests
(`tests/test_tools.py`) assert this is deterministic across repeated calls
and that unknown items never resolve to a price.

### Expected running cost (typical small-business volume)

Assuming a modest volume — a few hundred call-minutes/month, realistic for
a single-location furniture showroom:

| Item | Monthly cost estimate |
|---|---|
| LiveKit Cloud (Build tier, <1,000 agent-min/month) | **$0** |
| Sarvam STT+TTS (~300 min/month) | roughly $15-25 (Rs 1,300-2,000) |
| Gemini 2.5 Flash LLM (~300 min/month) | roughly $0.30-1.50 - negligible |
| SIP carrier trunk rental | ~Rs 500/month (~$6) |
| SIP carrier per-minute (~300 min blended in/out) | roughly Rs 150-450 (~$2-5) |
| Hosting the agent worker (small VM) | $0-6/month (many providers have a free tier sized for this) |
| **Total, typical month** | **roughly $25-40/month**, almost entirely Sarvam STT/TTS usage |

Once volume grows past LiveKit's free tier or you want HA hosting, add
LiveKit Ship ($50/mo) and a proper VM — but that's a "you're succeeding"
problem, not a starting cost.


## Project structure

```
bvhomes-voice-agent/
├── agent/
│   ├── main.py          # entrypoint: STT/LLM/TTS wiring, session lifecycle
│   ├── prompts.py        # builds the system prompt from business_data.py
│   ├── business_data.py  # product catalog + company facts (source of truth)
│   ├── tools.py           # LLM function-tools: save_lead, request_executive_callback
│   ├── storage.py         # async SQLite lead persistence
│   └── config.py           # env var loading + validation
├── telephony/
│   ├── inbound-trunk.json
│   ├── outbound-trunk.json
│   ├── dispatch-rule.json
│   └── README.md          # full SIP/phone-number setup guide
├── scripts/
│   └── eval_llm_telugu.py  # runnable Ollama-vs-Gemini side-by-side eval
├── tests/                  # pytest suite (19 tests, see below)
├── Dockerfile
├── pyproject.toml
├── .env.example
└── README.md               # this file
```

## What's fixed vs. what the agent is allowed to say

`business_data.py` is the **only** source of prices/products. **Pricing is
now enforced in code, not just prompt instruction:** the agent must call the
`get_product_price` tool (an exact Python dict lookup) before stating any
price — there is no code path that returns a number outside `PRODUCTS`.
Materials, warranty, delivery charges, delivery dates, discounts, and stock
availability are still governed by prompt instruction only (there's no
structured data for these yet — see **Known limitations**). For anything
outside the 7 catalog items, the agent offers customization (a real BVHomes
capability) and/or a callback — it does not guess.

Current catalog (edit `agent/business_data.py` to change):

| Product | Price |
|---|---|
| L-type sofa | ₹42,000 |
| Teak solid-wood king-size bed without box | ₹35,000 |
| L-corner sofa | ₹35,000 |
| Dining table | ₹32,000 |
| U-shape sofa | ₹55,000 |
| Double recliner | ₹42,000 |
| Convertible sofa bed | ₹42,000 |

## Setup

### 1. Install `uv`

```
curl -LsSf https://astral.sh/uv/install.sh | sh      # macOS/Linux
# or on Windows PowerShell:
# powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Install dependencies

```
cd bvhomes-voice-agent
uv sync --all-extras --dev
```

### 3. Configure environment

```
cp .env.example .env
```

Fill in `.env`:

| Variable | Required | Where to get it |
|---|---|---|
| `LIVEKIT_URL` | Yes | LiveKit Cloud dashboard → Settings → Project |
| `LIVEKIT_API_KEY` | Yes | same page |
| `LIVEKIT_API_SECRET` | Yes | same page |
| `SARVAM_API_KEY` | Yes | https://dashboard.sarvam.ai → API Keys |
| `GOOGLE_API_KEY` | No | only if bypassing LiveKit Inference for Gemini |
| `BVHOMES_LLM_PROVIDER` | No | `gemini` (default) or `ollama` — see Cost optimization section |
| `BVHOMES_OLLAMA_BASE_URL` | No | defaults to `http://localhost:11434/v1`; only used if provider is `ollama` |
| `BVHOMES_OLLAMA_MODEL` | No | defaults to `llama3.3:8b`; only used if provider is `ollama` |
| `BVHOMES_DB_PATH` | No | defaults to `data/leads.db` |
| `DATABASE_URL` | No | PostgreSQL DSN for production; when set, it overrides `BVHOMES_DB_PATH` |
| `BVHOMES_LOG_LEVEL` | No | defaults to `INFO` |
| `BVHOMES_TTS_SPEAKER` | No | defaults to `anushka`; see Sarvam voice list |

`agent/config.py` validates required vars at startup and fails with a clear
message listing exactly what's missing — it won't silently start broken.

## Running locally

**Mic/speaker test (no LiveKit room needed):**
```
uv run python -m agent.main console
```
Talk to it directly through your computer's mic/speakers. This is the
fastest way to sanity-check Telugu/English/Hindi behavior before wiring up
telephony.

**Connected to a real LiveKit room (e.g. testing from a web/mobile client):**
```
uv run python -m agent.main dev
```

**Production worker mode** (used for both telephony and app-based calls):
```
uv run python -m agent.main start
```

## Connecting a phone number (SIP)

Full step-by-step in **`telephony/README.md`** — short version:

1. Buy an Indian number + SIP trunk from a provider (Exotel, Twilio, Telnyx, Plivo)
2. `lk sip inbound create --request telephony/inbound-trunk.json`
3. `lk sip dispatch create --request telephony/dispatch-rule.json`
4. Point the SIP provider at your LiveKit project's SIP URI
5. Run the agent worker (`uv run python -m agent.main start`) — it auto-answers

## Cloud deployment

```
docker build -t bvhomes-agent .
docker run -d \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  --name bvhomes-agent \
  bvhomes-agent
```

The volume mount keeps `leads.db` across restarts/redeploys. Deploy this
container anywhere that can run a long-lived process reaching the public
internet (LiveKit Cloud workers just need outbound connectivity — no inbound
port required): a small VM, Fly.io, Railway, Render, ECS/Cloud Run, etc.
Point `LIVEKIT_URL`/keys at the same LiveKit project as your SIP trunk.

For scale-out, run multiple replicas of the same container — LiveKit's job
dispatch load-balances across all registered workers automatically; no
agent-side changes needed.

## Testing leads

Leads land in the SQLite DB at `BVHOMES_DB_PATH`. Quick inspection:
```
sqlite3 data/leads.db "SELECT id, name, phone_number, furniture_requirement, lead_type, created_at FROM leads ORDER BY id DESC;"
```

## Customer conversation dashboard

Every completed LiveKit session is saved in the same SQLite database as the
leads. It includes the rendered customer/agent transcript, a Gemini-generated
structured summary, topics, products, requirements, budget, lead status, and
follow-up action. A failed summary or database write is logged but never ends
an active voice call.

Start the local dashboard in a second terminal:

```
uv run python -m agent.dashboard
```

Open `http://127.0.0.1:8080`. The dashboard is intentionally local-only and
does not add any external or paid infrastructure. Its JSON API is also useful
for a future CRM integration:

```
GET /api/conversations
GET /api/conversations/{id}
GET /api/conversations?customer=Anita&date=2026-08-21&product=sofa&lead_status=qualified
```

### PostgreSQL production storage

SQLite remains the default for local testing. For production, provision any
PostgreSQL-compatible database and set one environment variable; no voice
agent setting changes are needed:

```
DATABASE_URL=postgresql://username:password@hostname:5432/bvhomes
```

`DATABASE_URL` takes precedence over `BVHOMES_DB_PATH`. On first start the
agent creates the same `leads` and `conversations` tables and indexes in
PostgreSQL. The dashboard and JSON API use the same selected database.

## Automated tests / static checks

```
uv run pytest tests/ -v
uv run ruff check .
```

Both were run during development of this repo: **19/19 tests pass** (12
from the original build, 7 added for the cost-optimization pass — pricing
determinism and LLM-provider config), ruff clean. All modules
(`business_data`, `storage`, `config`, `prompts`, `tools`, `main`) were also
verified to import cleanly against the real installed `livekit-agents`,
`livekit-plugins-sarvam`, and `livekit-plugins-openai` packages — including
building both the Gemini and Ollama LLM code paths — not just unit-tested
in isolation.

Tests cover: catalog price integrity (regression guard against the exact
spec prices), the ₹-symbol-avoidance rule for TTS, unknown-product lookups
correctly returning `None` (not a guess), deterministic price-lookup
behavior (same input always returns the same price, unknown items never
resolve to one), LLM provider config validation, and the SQLite lead store
(save/list, multiple leads per call, callback-type leads).

**Not covered by these tests** (see Known limitations): actual STT/TTS/LLM
behavior, since that requires live API calls and a microphone — this
environment has neither.

## Required environment variables (summary)

```
LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET   — LiveKit project
SARVAM_API_KEY                                      — Sarvam AI (STT+TTS)
```
Plus SIP trunk credentials from your chosen provider (Exotel/Twilio/Telnyx/
Plivo) for telephony — not an env var, configured in `telephony/*.json`.

## Remaining external credentials/services you need to provide

1. **LiveKit Cloud project** (or self-hosted LiveKit + SIP service) — Build
   tier free, sufficient to start.
2. **Sarvam AI account + API key** — free signup credits, then pay-as-you-go.
3. **A SIP trunking provider account with an Indian DID number** — required
   only for the phone-call step, not for local/console testing.
4. LiveKit Inference is used for Gemini by default, so no separate Google
   Cloud account is strictly required — only add `GOOGLE_API_KEY` if you
   want to call Gemini directly instead.

## Known limitations

- **No live voice testing was possible in this build environment** — there's
  no microphone/speaker or network access to Sarvam/LiveKit here. Everything
  STT/TTS/LLM-behavior-related (accuracy, naturalness, actual code-switching
  quality, actual barge-in feel) is implemented per official docs but
  **unverified against real audio**. Run `console` mode on your machine
  first and iterate on `prompts.py` / TTS speaker choice from what you hear.
- **Pricing is now code-enforced** (`get_product_price` tool, exact dict
  lookup) — this was a known limitation in the previous version and is now
  fixed. Materials, warranty, delivery charges/dates, discounts, and stock
  availability are still governed by prompt instruction only, since there's
  no structured data source for them yet. Same follow-up pattern
  (`get_X` tool backed by a plain Python dict) would harden those too, if
  BVHomes provides that data.
- **Ollama/local-LLM Telugu quality is unverified against live output** —
  the code path is fully wired and tested for *building* (imports cleanly,
  produces a valid LLM object, degrades gracefully when unreachable), and
  `scripts/eval_llm_telugu.py` gives you a real, run-yourself comparison
  harness — but no actual model *response* has been evaluated, since this
  sandbox has no network path to ollama.com or any model registry
  (confirmed directly, not assumed). Run the eval script on your own
  machine before trusting Ollama in production. It's off by default because
  published research shows Telugu is under-represented in the training data
  of every current open local model.
- **No deduplication of leads** — the same caller across multiple calls
  produces multiple rows by design (see `storage.py` docstring). Reconciling
  duplicates is left to whatever consumes this table (CRM import, staff
  review) rather than guessed at by the agent.
- **No outbound calling campaign scheduler** — the building block
  (`lk sip participant create`) is documented in `telephony/README.md`, but
  there's no automation triggering callbacks off the `leads` table yet.
- **Single SQLite file** — fine at BVHomes' call volume; would need a real
  DB (Postgres) before this could handle serious concurrent write load.
- **`inbound-trunk.json` / `outbound-trunk.json` / `dispatch-rule.json`
  contain placeholder values** (`+91XXXXXXXXXX`, trunk domain, auth
  credentials) that only you can fill in once you've picked a SIP provider —
  flagged clearly in `telephony/README.md`.
- Barge-in relies on `AgentSession`'s `turn_handling` interruption default
  (enabled) — the older `allow_interruptions=True` kwarg still exists but is
  deprecated in favor of `turn_handling=TurnHandlingOptions(...)`; confirmed
  via package inspection against the installed `livekit-agents` version. The
  actual *feel* of interruption handling with Sarvam's STT latency still
  needs your live-call judgment, not just a config flag.
