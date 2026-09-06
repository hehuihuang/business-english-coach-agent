from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from . import models, schemas
from .agent.graph import CoachGraph
from .agent.tools import call_mcp_tool
from .celery_app import evaluation_task, ingest_document_task
from .config import get_settings
from .database import Base, SessionLocal, engine, get_db
from .models import Role
from .security import (
    create_access_token,
    get_current_user,
    hash_password,
    issue_refresh_token,
    require_roles,
    rotate_refresh_token,
    verify_password,
)
from .seed import create_demo_users, seed_reference_data
from .services.evaluation import EvaluationService
from .services.evolution import EvolutionService
from .services.ingestion import ingest_document
from .services.memory import MemoryService
from .services.providers import SpeechProvider

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.database_url.startswith("postgresql"):
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        await seed_reference_data(db)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="A traceable Business English coaching agent built to teach production Agent engineering.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def token_pair(db: Session, user: models.User) -> schemas.TokenPair:
    return schemas.TokenPair(access_token=create_access_token(user), refresh_token=issue_refresh_token(db, user))


def owned_conversation(db: Session, conversation_id: str, user: models.User) -> models.Conversation:
    conversation = db.get(models.Conversation, conversation_id)
    if not conversation or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"ok": True, "service": settings.app_name, "provider": settings.ai_provider, "environment": settings.app_env}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post(f"{settings.api_prefix}/auth/register", response_model=schemas.TokenPair, status_code=201)
def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
    email = payload.email.lower()
    if db.scalar(select(models.User).where(models.User.email == email)):
        raise HTTPException(status_code=409, detail="Email is already registered")
    user = models.User(email=email, display_name=payload.display_name, password_hash=hash_password(payload.password))
    db.add(user)
    db.flush()
    db.add(models.LearnerProfile(user_id=user.id, goals=["communicate clearly at work"]))
    db.commit()
    return token_pair(db, user)


@app.post(f"{settings.api_prefix}/auth/login", response_model=schemas.TokenPair)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return token_pair(db, user)


@app.post(f"{settings.api_prefix}/auth/refresh", response_model=schemas.TokenPair)
def refresh(payload: schemas.RefreshRequest, db: Session = Depends(get_db)):
    user, new_refresh = rotate_refresh_token(db, payload.refresh_token)
    return schemas.TokenPair(access_token=create_access_token(user), refresh_token=new_refresh)


@app.get(f"{settings.api_prefix}/me")
def me(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = MemoryService(db).get_profile(user.id)
    return {
        "id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role,
        "profile": {"industry": profile.industry, "job_title": profile.job_title, "cefr_level": profile.cefr_level,
                    "goals": profile.goals, "preferences": profile.preferences, "skill_scores": profile.skill_scores},
    }


@app.put(f"{settings.api_prefix}/profile")
def update_profile(payload: schemas.ProfileUpdate, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = MemoryService(db).get_profile(user.id)
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    db.commit()
    return payload.model_dump()


@app.get(f"{settings.api_prefix}/memories")
def list_memories(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"id": item.id, "type": item.memory_type, "content": item.content, "confidence": item.confidence,
             "next_review_at": item.next_review_at, "enabled": item.enabled}
            for item in MemoryService(db).recall(user.id, limit=100)]


@app.put(f"{settings.api_prefix}/memories/{{memory_id}}")
def update_memory(memory_id: str, payload: schemas.MemoryUpdate, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    memory = db.get(models.LongTermMemory, memory_id)
    if not memory or memory.user_id != user.id:
        raise HTTPException(status_code=404, detail="Memory not found")
    memory.content, memory.enabled = payload.content, payload.enabled
    db.commit()
    return {"id": memory.id, "content": memory.content, "enabled": memory.enabled}


@app.post(f"{settings.api_prefix}/conversations", status_code=201)
def create_conversation(payload: schemas.ConversationCreate, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = models.Conversation(user_id=user.id, **payload.model_dump())
    db.add(item)
    db.commit()
    return {"id": item.id, "title": item.title, "mode": item.mode, "status": item.status}


@app.get(f"{settings.api_prefix}/conversations")
def list_conversations(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.scalars(select(models.Conversation).where(models.Conversation.user_id == user.id).order_by(models.Conversation.updated_at.desc())).all()
    return [{"id": item.id, "title": item.title, "mode": item.mode, "status": item.status, "updated_at": item.updated_at} for item in items]


@app.get(f"{settings.api_prefix}/conversations/{{conversation_id}}/messages")
def list_messages(conversation_id: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned_conversation(db, conversation_id, user)
    items = db.scalars(select(models.Message).where(models.Message.conversation_id == conversation_id).order_by(models.Message.created_at)).all()
    return [{"id": item.id, "role": item.role, "content": item.content, "metadata": item.metadata_json, "created_at": item.created_at} for item in items]


@app.post(f"{settings.api_prefix}/conversations/{{conversation_id}}/messages")
async def send_message(conversation_id: str, payload: schemas.MessageCreate, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned_conversation(db, conversation_id, user)
    try:
        run, state = await CoachGraph(db).run(user.id, conversation_id, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"run_id": run.id, "trace_id": run.trace_id, "content": state["response"], "plan": state["task_plan"],
            "assessment": state["assessment"], "citations": state.get("citations", []), "tool_events": state.get("tool_events", []),
            "usage": {"input_tokens": run.input_tokens, "output_tokens": run.output_tokens, "latency_ms": run.latency_ms}}


@app.post(f"{settings.api_prefix}/conversations/{{conversation_id}}/messages/stream")
async def stream_message(conversation_id: str, payload: schemas.MessageCreate, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned_conversation(db, conversation_id, user)

    async def event_stream():
        yield f"event: status\ndata: {json.dumps({'stage': 'planning'})}\n\n"
        try:
            run, state = await CoachGraph(db).run(user.id, conversation_id, payload.content)
            yield f"event: plan\ndata: {json.dumps(state['task_plan'], ensure_ascii=False)}\n\n"
            yield f"event: final\ndata: {json.dumps({'run_id': run.id, 'trace_id': run.trace_id, 'content': state['response'], 'assessment': state['assessment'], 'citations': state.get('citations', []), 'tool_events': state.get('tool_events', []), 'usage': {'input_tokens': run.input_tokens, 'output_tokens': run.output_tokens, 'latency_ms': run.latency_ms}}, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001 - SSE must serialize terminal failures instead of breaking the stream.
            yield f"event: error\ndata: {json.dumps({'type': type(exc).__name__, 'message': str(exc)[:300]})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post(f"{settings.api_prefix}/speech/transcriptions")
async def transcribe_audio(audio: UploadFile = File(...), user: models.User = Depends(get_current_user)):
    content = await audio.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio file is too large")
    return {"text": await SpeechProvider().transcribe(content, audio.filename or "audio.webm")}


@app.post(f"{settings.api_prefix}/speech/synthesis")
async def synthesize_audio(payload: schemas.MessageCreate, user: models.User = Depends(get_current_user)):
    audio = await SpeechProvider().synthesize(payload.content)
    return Response(audio, media_type="audio/mpeg")


@app.post(f"{settings.api_prefix}/knowledge/documents", status_code=202)
async def upload_document(
    title: str = Form(...), document: UploadFile = File(...),
    user: models.User = Depends(get_current_user), db: Session = Depends(get_db),
):
    suffix = Path(document.filename or "").suffix.lower()
    allowed = {".md": "text/markdown", ".txt": "text/plain", ".pdf": "application/pdf"}
    if suffix not in allowed:
        raise HTTPException(status_code=415, detail="Only Markdown, TXT, and PDF are supported")
    content = await document.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Document is too large")
    safe_path = settings.upload_dir / f"{uuid4()}{suffix}"
    safe_path.write_bytes(content)
    item = models.KnowledgeDocument(
        user_id=user.id, title=title[:240], filename=Path(document.filename or "document").name,
        content_type=allowed[suffix], source_path=str(safe_path),
    )
    db.add(item)
    db.commit()
    try:
        ingest_document_task.delay(item.id)
    except Exception:  # noqa: BLE001 - any broker failure activates the documented local fallback.
        # Development without Redis still has a useful, deterministic path.
        await ingest_document(db, item.id)
    return {"id": item.id, "status": item.status, "filename": item.filename}


@app.get(f"{settings.api_prefix}/knowledge/documents")
def list_documents(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.scalars(select(models.KnowledgeDocument).where(or_(models.KnowledgeDocument.user_id.is_(None), models.KnowledgeDocument.user_id == user.id))).all()
    return [{"id": item.id, "title": item.title, "filename": item.filename, "status": item.status, "version": item.version, "error": item.error} for item in items]


@app.get(f"{settings.api_prefix}/runs/{{run_id}}/trace")
def get_trace(run_id: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.get(models.AgentRun, run_id)
    if not run or (run.user_id != user.id and user.role not in {Role.ADMIN, Role.EVALUATOR}):
        raise HTTPException(status_code=404, detail="Run not found")
    events = db.scalars(select(models.TraceEvent).where(models.TraceEvent.run_id == run.id).order_by(models.TraceEvent.sequence)).all()
    return {"run": {"id": run.id, "trace_id": run.trace_id, "status": run.status, "latency_ms": run.latency_ms,
                    "input_tokens": run.input_tokens, "output_tokens": run.output_tokens, "error_type": run.error_type},
            "events": [{"sequence": e.sequence, "event_type": e.event_type, "name": e.name, "status": e.status,
                        "duration_ms": e.duration_ms, "payload": e.payload, "created_at": e.created_at} for e in events]}


@app.post(f"{settings.api_prefix}/tools/mcp/{{tool_name}}")
async def invoke_mcp(tool_name: str, payload: schemas.MCPToolRequest, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    policies = {
        "business_term_lookup": {"roles": {Role.LEARNER, Role.EVALUATOR, Role.ADMIN}, "confirmation": False},
        "company_material_search": {"roles": {Role.LEARNER, Role.EVALUATOR, Role.ADMIN}, "confirmation": False},
        "practice_schedule": {"roles": {Role.LEARNER, Role.EVALUATOR, Role.ADMIN}, "confirmation": True},
    }
    policy = policies.get(tool_name)
    if not policy or user.role not in policy["roles"]:
        raise HTTPException(status_code=403, detail="Tool is not allowed")
    arguments = dict(payload.arguments)
    if policy["confirmation"]:
        arguments["confirmed"] = payload.confirmed
    result = await call_mcp_tool(tool_name, arguments)
    db.add(models.AuditLog(actor_id=user.id, action="mcp.call", resource_type="tool", resource_id=tool_name,
                           detail={"status": result.get("status"), "confirmed": payload.confirmed}))
    db.commit()
    return result


@app.get(f"{settings.api_prefix}/dashboard")
def dashboard(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    run_filter = models.AgentRun.user_id == user.id if user.role == Role.LEARNER else text("1=1")
    total, failed = db.execute(select(func.count(models.AgentRun.id), func.sum((models.AgentRun.status == "failed").cast(models.Integer))).where(run_filter)).one()
    avg_latency = db.scalar(select(func.avg(models.AgentRun.latency_ms)).where(run_filter)) or 0
    return {"runs": total or 0, "failure_rate": (failed or 0) / total if total else 0, "average_latency_ms": round(avg_latency),
            "memories": db.scalar(select(func.count()).select_from(models.LongTermMemory).where(models.LongTermMemory.user_id == user.id)) or 0,
            "knowledge_documents": db.scalar(select(func.count()).select_from(models.KnowledgeDocument).where(or_(models.KnowledgeDocument.user_id.is_(None), models.KnowledgeDocument.user_id == user.id))) or 0}


@app.post(f"{settings.api_prefix}/evaluations", status_code=202)
async def create_evaluation(payload: schemas.EvaluationCreate, user: models.User = Depends(require_roles(Role.EVALUATOR, Role.ADMIN)), db: Session = Depends(get_db)):
    item = models.EvaluationRun(created_by=user.id, candidate_version=payload.candidate_version)
    db.add(item)
    db.commit()
    try:
        evaluation_task.delay(item.id)
    except Exception:  # noqa: BLE001 - any broker failure activates the documented local fallback.
        await EvaluationService(db).run(item)
    return {"id": item.id, "status": item.status}


@app.get(f"{settings.api_prefix}/evaluations")
def list_evaluations(user: models.User = Depends(require_roles(Role.EVALUATOR, Role.ADMIN)), db: Session = Depends(get_db)):
    items = db.scalars(select(models.EvaluationRun).order_by(models.EvaluationRun.created_at.desc())).all()
    return [{"id": item.id, "candidate_version": item.candidate_version, "status": item.status, "summary": item.summary, "created_at": item.created_at} for item in items]


@app.post(f"{settings.api_prefix}/evaluation-results/{{result_id}}/reviews", status_code=201)
def human_review(result_id: int, payload: schemas.HumanReviewCreate, user: models.User = Depends(require_roles(Role.EVALUATOR, Role.ADMIN)), db: Session = Depends(get_db)):
    if not db.get(models.EvaluationResult, result_id):
        raise HTTPException(status_code=404, detail="Evaluation result not found")
    item = models.HumanReview(evaluation_result_id=result_id, reviewer_id=user.id, **payload.model_dump())
    db.add(item)
    db.commit()
    return {"id": item.id}


@app.post(f"{settings.api_prefix}/improvements", status_code=201)
def create_improvement(payload: schemas.ImprovementCreate, user: models.User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = models.ImprovementProposal(
        created_by=user.id, candidate_version=f"candidate-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        **payload.model_dump(),
    )
    db.add(item)
    db.commit()
    return {"id": item.id, "candidate_version": item.candidate_version, "status": item.status}


@app.post(f"{settings.api_prefix}/improvements/generate", status_code=201)
def generate_improvement(user: models.User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = EvolutionService(db).generate_candidate(user.id)
    return {"id": item.id, "candidate_version": item.candidate_version, "status": item.status, "changes": item.changes}


@app.get(f"{settings.api_prefix}/improvements")
def list_improvements(user: models.User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    items = db.scalars(select(models.ImprovementProposal).order_by(models.ImprovementProposal.created_at.desc())).all()
    return [{"id": item.id, "type": item.proposal_type, "base_version": item.base_version,
             "candidate_version": item.candidate_version, "status": item.status,
             "changes": item.changes, "evaluation_summary": item.evaluation_summary} for item in items]


@app.post(f"{settings.api_prefix}/improvements/{{proposal_id}}/attach-evaluation/{{evaluation_id}}")
def attach_evaluation(proposal_id: str, evaluation_id: str, user: models.User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    proposal = db.get(models.ImprovementProposal, proposal_id)
    evaluation = db.get(models.EvaluationRun, evaluation_id)
    if not proposal or not evaluation or evaluation.status != "completed":
        raise HTTPException(status_code=404, detail="Completed evaluation or proposal not found")
    baseline = db.scalar(
        select(models.EvaluationRun)
        .where(models.EvaluationRun.candidate_version == proposal.base_version, models.EvaluationRun.status == "completed")
        .order_by(models.EvaluationRun.completed_at.desc())
    )
    baseline_score = (baseline.summary or {}).get("average_score", 0) if baseline else 0
    candidate_score = (evaluation.summary or {}).get("average_score", 0)
    proposal.evaluation_summary = {
        **evaluation.summary,
        "evaluation_id": evaluation.id,
        "baseline_score": baseline_score,
        "quality_gain": (candidate_score - baseline_score) / 100,
    }
    proposal.status = "ready_for_review"
    db.commit()
    return {"id": proposal.id, "status": proposal.status, "evaluation_summary": proposal.evaluation_summary}


@app.post(f"{settings.api_prefix}/improvements/{{proposal_id}}/approve")
def approve_improvement(proposal_id: str, payload: schemas.ReviewDecision, user: models.User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(models.ImprovementProposal, proposal_id)
    if not item:
        raise HTTPException(status_code=404, detail="Proposal not found")
    approved = EvolutionService(db).approve(item, user.id)
    return {"id": approved.id, "status": approved.status, "active_version": approved.candidate_version}


@app.post(f"{settings.api_prefix}/improvements/rollback")
def rollback_improvement(payload: schemas.ReviewDecision, user: models.User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    return EvolutionService(db).rollback(user.id)


@app.post(f"{settings.api_prefix}/demo/bootstrap")
def demo_bootstrap(db: Session = Depends(get_db)):
    if settings.app_env == "production":
        raise HTTPException(status_code=404, detail="Not found")
    return create_demo_users(db)
