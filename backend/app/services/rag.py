from __future__ import annotations

import math
import re
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import KnowledgeChunk, KnowledgeDocument


@dataclass
class SearchHit:
    chunk_id: str
    document_id: str
    title: str
    content: str
    score: float
    citation: str


def lexical_score(query: str, text: str) -> float:
    terms = {term for term in re.findall(r"[a-zA-Z]{2,}|[\u4e00-\u9fff]+", query.lower())}
    if not terms:
        return 0
    haystack = text.lower()
    return sum(1 for term in terms if term in haystack) / len(terms)


def cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0
    denominator = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return 0 if denominator == 0 else sum(x * y for x, y in zip(a, b)) / denominator


class KnowledgeService:
    def __init__(self, db: Session):
        self.db = db

    def search(self, user_id: str, query: str, query_embedding: list[float] | None = None, limit: int = 5) -> list[SearchHit]:
        rows = self.db.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(
                KnowledgeDocument.status == "ready",
                or_(KnowledgeDocument.user_id.is_(None), KnowledgeDocument.user_id == user_id),
            )
        ).all()
        scored = []
        for chunk, document in rows:
            lexical = lexical_score(query, chunk.content)
            semantic = max(0, cosine_similarity(query_embedding, chunk.embedding))
            score = 0.45 * lexical + 0.55 * semantic
            if score > 0:
                scored.append(SearchHit(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    title=document.title,
                    content=chunk.content,
                    score=round(score, 4),
                    citation=f"[{document.title} · §{chunk.ordinal + 1}]",
                ))
        return sorted(scored, key=lambda item: item.score, reverse=True)[:limit]
