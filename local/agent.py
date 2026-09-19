from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from openai import OpenAI

from agent.business_data import find_product
from local.rag import ingest_documents, search_knowledge

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("BVHOMES_LOCAL_DB", BASE_DIR / "data" / "bvhomes_local.db"))

SYSTEM = """You are Priya, the BVHomes Furniture local AI sales agent.

You speak naturally in Telugu, English, Hindi, and Telugu-English code-switching.
Keep spoken answers short and helpful.

BVHomes is a furniture manufacturer in Visakhapatnam, Andhra Pradesh.

Use tools instead of guessing:
- search_product for exact catalog prices.
- search_knowledge for BVHomes policies, FAQs, and documents.
- save_lead when enough customer details are available.
- request_callback for custom furniture, measurement visits, or human follow-up.

Never invent a price, warranty, delivery charge/date, discount, stock status, or
business policy. If the knowledge base does not contain the answer, offer a
human follow-up.

This is a local-first system. Customer data stays in the configured local
database unless the owner deliberately connects an external service.
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
        db.execute(
            """CREATE TABLE IF NOT EXISTS callbacks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                phone TEXT,
                reason TEXT,
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
        {"found": True, "name": product.name, "price_inr": product.price_inr},
        ensure_ascii=False,
    )


def search_kb(query: str) -> str:
    results = search_knowledge(query)
    return json.dumps(
        {"found": bool(results), "results": results},
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


def request_callback(name: str, phone: str, reason: str) -> str:
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute(
            "INSERT INTO callbacks (name, phone, reason) VALUES (?, ?, ?)",
            (name, phone, reason),
        )
        db.commit()
        return f"Callback request saved with id {cur.lastrowid}."


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_product",
            "description": "Find an exact BVHomes catalog product and confirmed price.",
            "parameters": {
                "type": "object",
                "properties": {"product_name": {"type": "string"}},
                "required": ["product_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Search local BVHomes documents and FAQs.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
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
    {
        "type": "function",
        "function": {
            "name": "request_callback",
            "description": "Create a human follow-up request for custom work or missing information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["name", "phone", "reason"],
            },
        },
    },
]


def run() -> None:
    init_db()
    ingest_documents()

    client = OpenAI(
        base_url=os.getenv("BVHOMES_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
        api_key="ollama",
    )
    model = os.getenv("BVHOMES_OLLAMA_MODEL", "qwen3.6:latest")
    messages = [{"role": "system", "content": SYSTEM}]

    print("BV Homes local agent")
    print(f"Model: {model}")
    print("RAG: local SQLite FTS5")
    print("Tools: product search, knowledge search, lead capture, callback")
    print("Type 'exit' to stop.\n")

    while True:
        user = input("Customer: ").strip()
        if user.lower() in {"exit", "quit"}:
            break
        if not user:
            continue

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
                elif call.function.name == "search_knowledge":
                    result = search_kb(args["query"])
                elif call.function.name == "save_lead":
                    result = save_lead(**args)
                elif call.function.name == "request_callback":
                    result = request_callback(**args)
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
