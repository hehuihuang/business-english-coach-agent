from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy.orm import Session

from ..models import KnowledgeChunk, KnowledgeDocument
from .providers import get_ai_provider


def extract_text(path: Path, content_type: str) -> str:
    if content_type == "application/pdf" or path.suffix.lower() == ".pdf":
        return "\n\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8")


def chunk_text(text: str, target_chars: int = 900, overlap_chars: int = 120) -> list[str]:
    """Paragraph-aware chunking with small overlap for cross-boundary recall."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > target_chars:
            chunks.append(current)
            current = current[-overlap_chars:] + "\n\n" + paragraph
        else:
            current = f"{current}\n\n{paragraph}".strip()
    if current:
        chunks.append(current)
    return chunks


async def ingest_document(db: Session, document_id: str):
    document = db.get(KnowledgeDocument, document_id)
    if not document:
        raise ValueError("Document not found")
    document.status = "processing"
    db.commit()
    try:
        chunks = chunk_text(extract_text(Path(document.source_path), document.content_type))
        embeddings = await get_ai_provider().embed(chunks)
        for ordinal, (content, embedding) in enumerate(zip(chunks, embeddings)):
            db.add(KnowledgeChunk(
                document_id=document.id,
                ordinal=ordinal,
                content=content,
                embedding=embedding,
                metadata_json={"filename": document.filename, "version": document.version},
            ))
        document.status = "ready"
        db.commit()
    except Exception as exc:
        document.status = "failed"
        document.error = f"{type(exc).__name__}: {exc}"[:1000]
        db.commit()
        raise
