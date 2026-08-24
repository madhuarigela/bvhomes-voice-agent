import pytest

from agent.storage import ConversationRecord, LeadRecord, LeadStore


@pytest.fixture
async def store(tmp_path):
    db_path = tmp_path / "test_leads.db"
    s = LeadStore(db_path)
    await s.init()
    return s


async def test_save_and_list_lead(store: LeadStore):
    lead = LeadRecord(
        room_name="bvhomes-call-test1",
        caller_number="+919999999999",
        name="Ramesh",
        phone_number="9999999999",
        furniture_requirement="L-type sofa",
        delivery_location="Visakhapatnam",
    )
    lead_id = await store.save_lead(lead)
    assert lead_id is not None

    leads = await store.list_leads()
    assert len(leads) == 1
    saved = leads[0]
    assert saved["name"] == "Ramesh"
    assert saved["furniture_requirement"] == "L-type sofa"
    assert saved["lead_type"] == "general"
    assert saved["status"] == "new"


async def test_callback_lead_type(store: LeadStore):
    lead = LeadRecord(
        room_name="bvhomes-call-test2",
        name="Lakshmi",
        phone_number="8888888888",
        furniture_requirement="custom wardrobe",
        lead_type="custom_callback",
        callback_reason="Item not in catalog, needs custom manufacture quote",
    )
    await store.save_lead(lead)

    leads = await store.list_leads()
    assert leads[0]["lead_type"] == "custom_callback"
    assert "custom manufacture" in leads[0]["callback_reason"]


async def test_multiple_leads_same_call_both_saved(store: LeadStore):
    # A single call may produce more than one row (partial capture, then
    # fuller capture later in the same call) — both must persist.
    room = "bvhomes-call-test3"
    await store.save_lead(LeadRecord(room_name=room, name="Suresh", phone_number="7777777777"))
    await store.save_lead(
        LeadRecord(
            room_name=room,
            name="Suresh",
            phone_number="7777777777",
            furniture_requirement="Dining table",
            budget="30000",
        )
    )
    leads = await store.list_leads()
    assert len(leads) == 2
    assert all(row["room_name"] == room for row in leads)


async def test_list_leads_ordering_most_recent_first(store: LeadStore):
    await store.save_lead(LeadRecord(room_name="r1", name="First"))
    await store.save_lead(LeadRecord(room_name="r2", name="Second"))
    leads = await store.list_leads()
    assert leads[0]["name"] == "Second"
    assert leads[1]["name"] == "First"


async def test_save_and_filter_completed_conversation(store: LeadStore):
    record = ConversationRecord(
        room_name="completed-room",
        customer_name="Anita",
        customer_phone="9000000000",
        started_at="2026-08-21T10:00:00+00:00",
        ended_at="2026-08-21T10:02:00+00:00",
        duration_seconds=120,
        transcript="Customer: Need a dining table",
        ai_summary="Customer wants a dining table.",
        topics_discussed="price, delivery",
        products_discussed="Dining table",
        budget="30000",
        requirements="Dining table for four people",
        lead_status="qualified",
        follow_up_action="Executive to confirm delivery",
    )
    conversation_id = await store.save_conversation(record)
    assert conversation_id is not None

    rows = await store.list_conversations(customer="Anita", product="Dining", lead_status="qualified")
    assert len(rows) == 1
    assert rows[0]["duration_seconds"] == 120
    assert rows[0]["requirements"] == "Dining table for four people"

    fetched = await store.get_conversation(rows[0]["id"])
    assert fetched is not None
    assert fetched["transcript"] == "Customer: Need a dining table"


async def test_conversation_room_is_saved_once_on_repeated_shutdown(store: LeadStore):
    record = ConversationRecord(
        room_name="same-room",
        started_at="2026-08-21T10:00:00+00:00",
        ended_at="2026-08-21T10:01:00+00:00",
        duration_seconds=60,
        transcript="first",
    )
    await store.save_conversation(record)
    record.transcript = "updated"
    await store.save_conversation(record)
    rows = await store.list_conversations()
    assert len(rows) == 1
    assert rows[0]["transcript"] == "updated"
