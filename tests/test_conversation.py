from livekit.agents import llm

from agent.conversation import transcript_from_history


def test_transcript_from_history_keeps_customer_and_agent_messages_only():
    history = llm.ChatContext.empty()
    history.add_message(role="system", content="private instructions")
    history.add_message(role="user", content="I need a sofa")
    history.add_message(role="assistant", content="Sure, which size?")

    assert transcript_from_history(history) == (
        "Customer: I need a sofa\nBVHomes Agent: Sure, which size?"
    )
