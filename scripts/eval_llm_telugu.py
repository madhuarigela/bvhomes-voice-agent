"""
Side-by-side LLM evaluation: Ollama (local) vs Gemini 2.5 Flash, on real
Telugu / Telugu-English code-switch / Hindi prompts representative of a
BVHomes sales call.

WHY THIS SCRIPT EXISTS:
This project's engineering decision (Gemini as default LLM, Ollama as
opt-in) is based on published research showing open local models are
weak specifically on Telugu. That's a reasonable starting point, but it's
not a substitute for testing on YOUR actual hardware with YOUR actual
prompts — model quality shifts fast, and "Telugu is low-resource" doesn't
tell you whether a specific model/quantization is good enough for BVHomes'
specific vocabulary (sofa, rupees, delivery, measurements).

Run this yourself before trusting either provider in production:

    ollama pull llama3.3:8b          # or any model you want to evaluate
    ollama serve                      # in a separate terminal
    uv sync --extra ollama
    uv run python scripts/eval_llm_telugu.py

It prints both models' responses to the same set of prompts side by side so
you can judge Telugu fluency, code-switch naturalness, and price-tool
discipline yourself. It does NOT score or auto-judge quality — that
judgment needs a Telugu speaker's ear, not a heuristic.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time

from livekit.agents import llm

from agent.prompts import build_system_instructions

logger = logging.getLogger("bvhomes-eval")

# Prompts chosen to stress the exact things BVHomes needs: Telugu fluency,
# mid-sentence code-switching, a price question (should trigger the
# get_product_price tool discipline), and an out-of-catalog item (should
# NOT invent a price).
TEST_PROMPTS = [
    (
        "Telugu price question",
        "L-type sofa ki price entha? Delivery kuda chestara?",
    ),
    (
        "Pure Telugu, measurements unknown",
        "నాకు సోఫా కావాలి కానీ సైజు తెలియదు. ఏం చేయాలి?",
    ),
    (
        "Code-switched, custom item (not in catalog)",
        "Naaku oka custom TV unit kavali, wall mount type. Cheyagalara?",
    ),
    (
        "Hindi",
        "Aapke paas dining table hai kya? Kitne ka hai?",
    ),
    (
        "English, lead capture flow",
        "I want the double recliner, 2 pieces, deliver to Visakhapatnam.",
    ),
]


async def run_one(model_llm: llm.LLM, system_prompt: str, user_text: str) -> tuple[str, float]:
    chat_ctx = llm.ChatContext.empty()
    chat_ctx.add_message(role="system", content=system_prompt)
    chat_ctx.add_message(role="user", content=user_text)

    start = time.monotonic()
    response = await model_llm.chat(chat_ctx=chat_ctx).collect()
    elapsed = time.monotonic() - start

    text = ""
    if response.chat_message and response.chat_message.text_content:
        text = response.chat_message.text_content
    return text, elapsed


async def main() -> None:
    system_prompt = build_system_instructions()

    providers: list[tuple[str, llm.LLM]] = []

    # Gemini via LiveKit Inference — always available if LIVEKIT_* env vars are set.
    try:
        from livekit.agents import inference

        providers.append(("Gemini 2.5 Flash", inference.LLM("google/gemini-2.5-flash")))
    except Exception as e:
        logger.exception("Gemini provider unavailable")
        print(f"[skip] Gemini unavailable: {e}")

    # Ollama — only if reachable, so this script degrades gracefully if you
    # haven't set it up yet.
    try:
        from livekit.plugins import openai as openai_plugin

        import agent.config as cfgmod

        cfg = cfgmod.load_config()
        providers.append(
            (
                f"Ollama ({cfg.ollama_model})",
                openai_plugin.LLM(
                    model=cfg.ollama_model,
                    base_url=cfg.ollama_base_url,
                    api_key="ollama",
                ),
            )
        )
    except Exception as e:
        logger.exception("Ollama provider unavailable")
        print(f"[skip] Ollama unavailable: {e}")

    if not providers:
        print("No LLM providers available — check your .env and Ollama setup.")
        sys.exit(1)

    print(f"Evaluating {len(providers)} provider(s) on {len(TEST_PROMPTS)} prompts.\n")

    for label, prompt_text in TEST_PROMPTS:
        print("=" * 70)
        print(f"PROMPT [{label}]: {prompt_text}")
        print("=" * 70)
        for provider_name, model_llm in providers:
            try:
                text, elapsed = await run_one(model_llm, system_prompt, prompt_text)
                print(f"\n--- {provider_name} ({elapsed:.2f}s) ---")
                print(text.strip() or "(empty response)")
            except Exception as e:
                logger.exception(f"{provider_name} call failed")
                print(f"\n--- {provider_name}: FAILED ({e}) ---")
        print()

    print(
        "\nDone. Judge Telugu fluency, code-switch naturalness, and whether "
        "prices came with a tool call (check agent logs, not this output, "
        "for actual tool-call traces) yourself — this script only surfaces "
        "the raw text so a Telugu speaker can compare quality directly."
    )


if __name__ == "__main__":
    asyncio.run(main())
