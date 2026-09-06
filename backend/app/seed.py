from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import GoldenCase, KnowledgeChunk, KnowledgeDocument, SystemSetting, User
from .security import hash_password
from .services.ingestion import chunk_text
from .services.providers import get_ai_provider

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent


def golden_set_path() -> Path:
    local_path = PROJECT_ROOT / "evals/golden_set.jsonl"
    return local_path if local_path.exists() else Path("/evals/golden_set.jsonl")


async def seed_reference_data(db: Session):
    if not db.scalar(select(func.count()).select_from(GoldenCase)):
        with golden_set_path().open(encoding="utf-8") as handle:
            for line in handle:
                item = json.loads(line)
                item["input_text"] = item.pop("input")
                db.add(GoldenCase(**item))

    if not db.scalar(select(func.count()).select_from(KnowledgeDocument)):
        source = BACKEND_ROOT / "data/seed/business_english_playbook.md"
        document = KnowledgeDocument(
            title="Business English Field Notes", filename=source.name,
            content_type="text/markdown", status="processing", source_path=str(source),
        )
        db.add(document)
        db.flush()
        chunks = chunk_text(source.read_text(encoding="utf-8"))
        embeddings = await get_ai_provider().embed(chunks)
        for ordinal, (content, embedding) in enumerate(zip(chunks, embeddings)):
            db.add(KnowledgeChunk(
                document_id=document.id, ordinal=ordinal, content=content, embedding=embedding,
                metadata_json={"built_in": True},
            ))
        document.status = "ready"

    if not db.get(SystemSetting, "active_prompt_version"):
        db.add(SystemSetting(key="active_prompt_version", value={"version": "coach-v1", "previous": None}))
    if not db.get(SystemSetting, "evolution_gates"):
        db.add(SystemSetting(key="evolution_gates", value={}))
    db.commit()


def create_demo_users(db: Session) -> dict:
    credentials = [
        ("learner@example.com", "Demo Learner", "learner"),
        ("admin@example.com", "Demo Evaluator", "admin"),
    ]
    result = {}
    for email, name, role in credentials:
        user = db.scalar(select(User).where(User.email == email))
        if not user:
            user = User(email=email, display_name=name, role=role, password_hash=hash_password("learn-english"))
            db.add(user)
            db.flush()
        result[role] = {"email": email, "password": "learn-english", "user_id": user.id}
    db.commit()
    return result
