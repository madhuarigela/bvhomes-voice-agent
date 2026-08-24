import pytest

from agent.business_data import PRODUCTS, find_product
from agent.storage import LeadStore
from agent.tools import save_callback_request, save_lead_record


@pytest.fixture
async def store(tmp_path):
    db_path = tmp_path / "test_leads.db"
    s = LeadStore(db_path)
    await s.init()
    return s


async def test_save_lead_record(store: LeadStore):
    lead_id = await save_lead_record(
        store,
        room_name="bvhomes-call-abc",
        name="Anita",
        phone_number="9000000000",
        furniture_requirement="U-shape sofa",
    )
    assert lead_id is not None
    leads = await store.list_leads()
    assert leads[0]["lead_type"] == "general"
    assert leads[0]["name"] == "Anita"


async def test_save_callback_request(store: LeadStore):
    lead_id = await save_callback_request(
        store,
        room_name="bvhomes-call-xyz",
        reason="Customer wants a custom bookshelf, not in catalog",
        name="Kiran",
        phone_number="9111111111",
    )
    assert lead_id is not None
    leads = await store.list_leads()
    assert leads[0]["lead_type"] == "custom_callback"
    assert "bookshelf" in leads[0]["callback_reason"]


# --- Deterministic pricing tests ---
# get_product_price is a @function_tool method (needs a RunContext to call
# directly), so these tests exercise the same deterministic lookup logic it
# delegates to: agent.business_data.find_product. This is what guarantees
# the agent can never state an invented price — the tool has no path that
# returns a number that isn't in PRODUCTS.

def test_all_catalog_items_resolve_to_their_exact_price():
    for product in PRODUCTS:
        found = find_product(product.name)
        assert found is not None
        assert found.price_inr == product.price_inr


def test_unknown_item_never_resolves_to_a_price():
    for query in ["wardrobe", "TV unit", "office chair", "bookshelf", "study table"]:
        assert find_product(query) is None


def test_price_lookup_is_deterministic_across_repeated_calls():
    # Same input must always give the same output — no randomness, no LLM
    # involved in this path at all.
    results = {find_product("L-type sofa").price_inr for _ in range(20)}
    assert results == {42000}
