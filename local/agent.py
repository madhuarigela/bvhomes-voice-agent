from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from openai import OpenAI

from agent.business_data import find_product, PRODUCTS

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("BVHOMES_LOCAL_DB", BASE_DIR / "data" / "bvhomes_local.db"))

SYSTEM = """You are Priya, the BVHomes Furniture local AI sales agent.

You speak naturally in Telugu, English, Hindi, and Telugu-English code-switching.
Keep spoken answers short and helpful.

BVHomes is a furniture manufacturer in Visakhapatnam, Andhra Pradesh.
The product catalog is available through the search_product tool.

Rules:
- Never invent a price.
- Use search_product before quoting a catalog price.
- For products outside the catalog, explain that BVHomes supports customization.
- Collect name, phone number, furniture requirement, budget, size and delivery
  location naturally during a sales conversation.
- Save a lead once enough information is available.
- If a customer asks for a measurement visit or custom follow-up, create a callback.
"""


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                phone TEXT,
                requirement TEXT,
                budget TEXT,
                size TEXT,
                delivery_location TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        db.commit()


def search_product(product_name: str) -> str:
    product = find_product(product_name)
    if product is None:
        return json.dumps(
            {"found": False, "message": "Not in catalog; customization is available."},
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "found": True,
            "name": product.name,
            "price_inr": product.price_inr,
        },
        ensure_ascii=False,
    )


def save_lead(
    name: str,
    phone: str,
    requirement: str,
    budget: str = "",
    size: str = "",
    delivery_location: str = "",
    notes: str = "",
) -> str:
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute(
            """INSERT INTO leads
            (name, phone, requirement, budget, size, delivery_location, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, phone, requirement, budget, size, delivery_location, notes),
        )
        db.commit()
        return f"Lead saved with id {cur.lastrowid}."


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_product",
            "description": "Find an exact BVHomes catalog product and confirmed price.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string"},
                },
                "required": ["product_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_lead",
            "description": "Save a BVHomes customer lead after enough details are collected.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "requirement": {"type": "string"},
                    "budget": {"type": "string"},
                    "size": {"type": "string"},
                    "delivery_location": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["name", "phone", "requirement"],
            },
        },
    },
]


def run() -> None:
    init_db()
    client = OpenAI(
        base_url=os.getenv("BVHOMES_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
        api_key="ollama",
    )
    model = os.getenv("BVHOMES_OLLAMA_MODEL", "qwen3.6:latest")

    messages = [{"role": "system", "content": SYSTEM}]

    print("BV Homes local agent")
    print(f"Model: {model}")
    print("Type 'exit' to stop.\n")

    while True:
        user = input("Customer: ").strip()
        if user.lower() in {"exit", "quit"}:
            break

        messages.append({"role": "user", "content": user})

        while True:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                temperature=0.2,
            )
            msg = response.choices[0].message

            if not msg.tool_calls:
                answer = msg.content or ""
                print(f"Priya: {answer}\n")
                messages.append({"role": "assistant", "content": answer})
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in msg.tool_calls
                    ],
                }
            )

            for call in msg.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                if call.function.name == "search_product":
                    result = search_product(args["product_name"])
                elif call.function.name == "save_lead":
                    result = save_lead(**args)
                else:
                    result = "Unknown tool."

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result,
                    }
                )


if __name__ == "__main__":
    run()
