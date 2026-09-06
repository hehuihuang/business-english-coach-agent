from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import LearnerProfile, LongTermMemory


def canonicalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:160] or "memory"


class MemoryService:
    def __init__(self, db: Session):
        self.db = db

    def get_profile(self, user_id: str) -> LearnerProfile:
        profile = self.db.get(LearnerProfile, user_id)
        if profile is None:
            profile = LearnerProfile(user_id=user_id, goals=["communicate clearly at work"])
            self.db.add(profile)
            self.db.commit()
        return profile

    def recall(self, user_id: str, limit: int = 8) -> list[LongTermMemory]:
        return list(self.db.scalars(
            select(LongTermMemory)
            .where(LongTermMemory.user_id == user_id, LongTermMemory.enabled.is_(True))
            .order_by(LongTermMemory.updated_at.desc())
            .limit(limit)
        ))

    def remember(
        self,
        user_id: str,
        memory_type: str,
        content: str,
        *,
        key: str | None = None,
        confidence: float = 0.7,
        source_message_id: str | None = None,
    ) -> LongTermMemory:
        canonical_key = canonicalize(key or content[:100])
        existing = self.db.scalar(select(LongTermMemory).where(
            LongTermMemory.user_id == user_id,
            LongTermMemory.memory_type == memory_type,
            LongTermMemory.canonical_key == canonical_key,
        ))
        review_time = datetime.now(UTC) + timedelta(days=1)
        if existing:
            # New evidence replaces stale wording only when it is at least as
            # confident; this avoids a single hallucinated turn corrupting profile.
            if confidence >= existing.confidence:
                existing.content = content
                existing.confidence = confidence
                existing.source_message_id = source_message_id
            existing.next_review_at = review_time
            memory = existing
        else:
            memory = LongTermMemory(
                user_id=user_id,
                memory_type=memory_type,
                canonical_key=canonical_key,
                content=content,
                confidence=max(0, min(confidence, 1)),
                source_message_id=source_message_id,
                next_review_at=review_time,
            )
            self.db.add(memory)
        self.db.commit()
        return memory
