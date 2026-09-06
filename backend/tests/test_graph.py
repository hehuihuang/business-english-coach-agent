import pytest

from app.agent.graph import CoachGraph, basic_assessment, infer_intent
from app.models import Conversation, KnowledgeChunk, KnowledgeDocument, User
from app.security import hash_password


@pytest.mark.asyncio
async def test_graph_runs_full_trace_and_persists_messages(db):
    user = User(email="coach@example.com", display_name="Coach", password_hash=hash_password("long-password"))
    db.add(user); db.flush()
    conversation = Conversation(user_id=user.id, mode="coach")
    document = KnowledgeDocument(title="Notes", filename="notes.md", content_type="text/markdown", status="ready")
    db.add_all([conversation, document]); db.flush()
    db.add(KnowledgeChunk(document_id=document.id, ordinal=0, content="Meeting disagreement should offer an alternative."))
    db.commit()

    run, state = await CoachGraph(db).run(user.id, conversation.id, "I work in sales. Help with a meeting disagreement.")
    assert run.status == "completed"
    assert state["intent"] == "roleplay"
    assert state["response"]
    assert len(run.trace_id) == 36
    assert state["assessment"]["word_count"] > 0


def test_intent_and_assessment_are_deterministic():
    assert infer_intent("Please rewrite this email", "coach") == "writing"
    assert infer_intent("anything", "diagnostic") == "diagnostic"
    assert basic_assessment("Could you send it by Friday?")["business_tone"] == 4
