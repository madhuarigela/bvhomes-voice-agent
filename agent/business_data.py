"""
Single source of truth for BVHomes Furniture business facts.

IMPORTANT: The agent must never invent prices, materials, warranty terms,
delivery charges, delivery dates, discounts, or availability that are not
present here. If a customer asks about something not in this file, the
agent's instructions (see prompts.py) direct it to offer a callback instead
of guessing.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    name: str
    price_inr: int
    notes: str = ""


BUSINESS_INFO = {
    "name": "BVHomes Furniture",
    "type": "Furniture manufacturer",
    "address": "Adavivaram, Pineapple Colony, Visakhapatnam, Andhra Pradesh",
    "phone": "7702 702 888",
    "offers_customization": True,
    "offers_delivery": True,
}

# All confirmed catalog items. Prices are fixed, confirmed values only.
PRODUCTS: list[Product] = [
    Product("L-type sofa", 42000),
    Product("Teak solid-wood king-size bed without box", 35000),
    Product("L-corner sofa", 35000),
    Product("Dining table", 32000),
    Product("U-shape sofa", 55000),
    Product("Double recliner", 42000),
    Product("Convertible sofa bed", 42000),
]


def format_catalog_for_prompt() -> str:
    """Render the catalog as plain-language lines for the LLM system prompt.

    Prices are written out as words-friendly digit groups (e.g. "42,000")
    rather than with a currency symbol, since TTS engines pronounce plain
    numbers followed by the word "rupees" far more reliably than the ₹ glyph.
    """
    lines = []
    for p in PRODUCTS:
        line = f"- {p.name}: {p.price_inr:,} rupees"
        if p.notes:
            line += f" ({p.notes})"
        lines.append(line)
    return "\n".join(lines)


def _normalize(text: str) -> str:
    """Lowercase and collapse hyphens/extra whitespace so 'L-type sofa' and
    'l type sofa' compare equal."""
    return " ".join(text.lower().replace("-", " ").split())


def find_product(query: str) -> Product | None:
    """Best-effort case/hyphen-insensitive substring match against the catalog.

    Returns None if nothing matches closely enough — callers must treat a
    None result as "not in catalog", never as "price unknown, guess one".
    """
    q = _normalize(query)
    if not q:
        return None
    for p in PRODUCTS:
        name = _normalize(p.name)
        if q in name or name in q:
            return p
    return None
