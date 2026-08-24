"""LLM-callable tools for the BVHomes agent.

Business logic lives in plain async functions (save_lead_record /
save_callback_request) so it can be unit-tested directly without needing a
live RunContext. The @function_tool-decorated methods on BVHomesTools are
thin wrappers the LLM actually calls during a session.
"""

from __future__ import annotations

import logging

from livekit.agents import RunContext
from livekit.agents.llm import function_tool

from agent.business_data import find_product
from agent.storage import LeadRecord, LeadStore

logger = logging.getLogger("bvhomes-agent.tools")


async def save_lead_record(store: LeadStore, room_name: str, **fields) -> int:
    lead = LeadRecord(room_name=room_name, lead_type="general", **fields)
    return await store.save_lead(lead)


async def save_callback_request(
    store: LeadStore, room_name: str, reason: str, **fields
) -> int:
    lead = LeadRecord(
        room_name=room_name,
        lead_type="custom_callback",
        callback_reason=reason,
        **fields,
    )
    return await store.save_lead(lead)


class BVHomesTools:
    """Holds the LeadStore + room context and exposes function_tool methods.

    Instantiated once per call/session in main.py, then its bound methods
    are passed into the Agent's tools list.
    """

    def __init__(self, store: LeadStore, room_name: str) -> None:
        self._store = store
        self._room_name = room_name

    @function_tool
    async def get_product_price(self, context: RunContext, product_name: str) -> str:
        """Look up the exact confirmed price for a BVHomes product. You MUST
        call this tool before stating any price out loud — never state a
        price from memory or by guessing. If this tool reports the item is
        not in the catalog, tell the customer BVHomes can custom-manufacture
        it instead of stating any price.

        Args:
            product_name: The furniture item the customer asked about, in
                their own words (e.g. "sofa", "L type sofa", "dining table")
        """
        product = find_product(product_name)
        if product is None:
            logger.info(f"Price lookup miss for {product_name!r}")
            return (
                f"NOT_IN_CATALOG: '{product_name}' is not a listed BVHomes product. "
                "Do not state a price. Tell the customer BVHomes can custom-manufacture "
                "this and offer to arrange an executive follow-up."
            )
        logger.info(f"Price lookup hit: {product.name} = {product.price_inr}")
        return f"CONFIRMED_PRICE: {product.name} is {product.price_inr:,} rupees."

    @function_tool
    async def save_lead(
        self,
        context: RunContext,
        name: str = "",
        phone_number: str = "",
        furniture_requirement: str = "",
        design: str = "",
        quantity: str = "",
        size: str = "",
        budget: str = "",
        delivery_location: str = "",
        special_requirements: str = "",
    ) -> str:
        """Save or update the customer's lead details captured so far during
        this call. Call this once you have at least a name, phone number,
        and furniture requirement. You may call it again later in the same
        call if the customer shares more details.

        Args:
            name: Customer's name
            phone_number: Customer's contact phone number, repeated back to confirm
            furniture_requirement: What furniture they want (e.g. "L-type sofa", "custom TV unit")
            design: Any design preference mentioned
            quantity: How many pieces, if relevant
            size: Size/dimensions, if the customer knows them
            budget: Budget mentioned by the customer, if any
            delivery_location: City/area for delivery
            special_requirements: Anything else notable (color, material, timeline, etc.)
        """
        try:
            lead_id = await save_lead_record(
                self._store,
                self._room_name,
                caller_number=phone_number,
                name=name,
                phone_number=phone_number,
                furniture_requirement=furniture_requirement,
                design=design,
                quantity=quantity,
                size=size,
                budget=budget,
                delivery_location=delivery_location,
                special_requirements=special_requirements,
            )
            return f"Lead saved (id {lead_id})."
        except Exception:
            logger.exception("Failed to save lead")
            # Don't let a storage failure break the conversation flow — the
            # LLM will still have said the right things to the customer.
            return "There was a problem saving the lead, but please continue the conversation naturally."

    @function_tool
    async def request_executive_callback(
        self,
        context: RunContext,
        reason: str,
        name: str = "",
        phone_number: str = "",
        furniture_requirement: str = "",
        delivery_location: str = "",
    ) -> str:
        """Flag this conversation for a BVHomes executive follow-up — use this
        for custom/unlisted furniture requests, when the customer needs a
        measurement visit, or any other request you can't fully handle from
        the catalog alone.

        Args:
            reason: Short summary of why a human needs to follow up
            name: Customer's name, if known
            phone_number: Customer's contact number, if known
            furniture_requirement: What they're asking about
            delivery_location: City/area, if mentioned
        """
        try:
            lead_id = await save_callback_request(
                self._store,
                self._room_name,
                reason=reason,
                caller_number=phone_number,
                name=name,
                phone_number=phone_number,
                furniture_requirement=furniture_requirement,
                delivery_location=delivery_location,
            )
            return f"Callback request saved (id {lead_id}). Let the customer know someone will reach out."
        except Exception:
            logger.exception("Failed to save callback request")
            return "There was a problem saving the callback request, but please continue the conversation naturally."
