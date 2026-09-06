import pytest

from app.agent.tools import ToolDefinition, ToolPermissionError, ToolRegistry
from app.models import User
from app.security import create_access_token, hash_password, verify_password


def test_password_and_access_token(db):
    encoded = hash_password("safe-password")
    assert verify_password("safe-password", encoded)
    assert not verify_password("wrong-password", encoded)
    user = User(email="u@example.com", display_name="User", password_hash=encoded)
    db.add(user); db.commit()
    assert create_access_token(user)


@pytest.mark.asyncio
async def test_tool_registry_enforces_scope_and_confirmation():
    async def handler(topic: str): return {"status": "scheduled", "topic": topic}
    registry = ToolRegistry()
    registry.register(ToolDefinition("schedule", "schedule_write", handler, requires_confirmation=True))
    with pytest.raises(ToolPermissionError):
        await registry.call("schedule", {"topic": "negotiation"}, set())
    pending = await registry.call("schedule", {"topic": "negotiation"}, {"schedule_write"})
    assert pending["status"] == "confirmation_required"
    completed = await registry.call("schedule", {"topic": "negotiation"}, {"schedule_write"}, confirmed=True)
    assert completed["status"] == "scheduled"
