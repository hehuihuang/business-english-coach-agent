from app.models import KnowledgeChunk, KnowledgeDocument, User
from app.security import hash_password
from app.services.memory import MemoryService
from app.services.rag import KnowledgeService, lexical_score


def make_user(db, email="learner@example.com"):
    user = User(email=email, display_name="Learner", password_hash=hash_password("long-password"))
    db.add(user)
    db.commit()
    return user


def test_memory_is_deduplicated_and_stronger_evidence_wins(db):
    user = make_user(db)
    service = MemoryService(db)
    first = service.remember(user.id, "profile", "I work in retail", key="industry", confidence=.8)
    second = service.remember(user.id, "profile", "I might work in finance", key="industry", confidence=.4)
    assert first.id == second.id
    assert second.content == "I work in retail"
    assert second.confidence == .8


def test_knowledge_search_is_user_scoped_and_cited(db):
    alice = make_user(db, "alice@example.com")
    bob = make_user(db, "bob@example.com")
    private = KnowledgeDocument(user_id=alice.id, title="Alice handbook", filename="a.md", content_type="text/markdown", status="ready")
    public = KnowledgeDocument(title="Field Notes", filename="public.md", content_type="text/markdown", status="ready")
    db.add_all([private, public]); db.flush()
    db.add_all([
        KnowledgeChunk(document_id=private.id, ordinal=0, content="Confidential launch language"),
        KnowledgeChunk(document_id=public.id, ordinal=0, content="A clear request includes an action and deadline"),
    ]); db.commit()
    results = KnowledgeService(db).search(bob.id, "clear request deadline")
    assert [item.title for item in results] == ["Field Notes"]
    assert results[0].citation == "[Field Notes · §1]"
    assert lexical_score("clear deadline", "Clear requests need a deadline") == 1
