from __future__ import annotations

import asyncio
import re
import time
from datetime import UTC, datetime
from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AgentRun, Conversation, Message, RunStatus
from ..observability import AGENT_RUNS, MODEL_TOKENS, NODE_LATENCY, TraceRecorder
from ..services.memory import MemoryService
from ..services.providers import AIProvider, get_ai_provider
from ..services.rag import KnowledgeService
from .checkpointing import checkpoint_context
from .prompts import build_coach_prompt
from .state import CoachState


def infer_intent(text: str, mode: str) -> str:
    lowered = text.lower()
    if mode != "coach":
        return mode
    if any(word in lowered for word in ["email", "邮件", "rewrite", "润色"]):
        return "writing"
    if any(word in lowered for word in ["interview", "面试", "meeting", "会议", "negotiate", "谈判"]):
        return "roleplay"
    if any(word in lowered for word in ["test me", "quiz", "复习", "测验"]):
        return "review"
    return "coach"


def basic_assessment(text: str) -> dict[str, Any]:
    words = re.findall(r"[A-Za-z']+", text)
    has_action = bool(re.search(r"\b(please|could|would|let's|by|before|next step)\b", text, re.IGNORECASE))
    return {
        "clarity": min(5, 2 + len(words) // 8),
        "business_tone": 4 if has_action else 3,
        "specificity": 4 if re.search(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|today|tomorrow|\d+)\b", text, re.IGNORECASE) else 3,
        "word_count": len(words),
    }


class CoachGraph:
    """Builds one graph around a request-scoped SQLAlchemy session.

    Passing dependencies into node closures makes I/O explicit and testable while
    LangGraph owns orchestration, routing and state transitions.
    """

    def __init__(self, db: Session, provider: AIProvider | None = None):
        self.db = db
        self.provider = provider or get_ai_provider()
        self.memory = MemoryService(db)
        self.knowledge = KnowledgeService(db)
        self.settings = get_settings()
        self.recorder: TraceRecorder | None = None

    def _trace(self, node: str, started: float, payload: dict[str, Any] | None = None):
        duration = int((time.perf_counter() - started) * 1000)
        NODE_LATENCY.labels(node=node).observe(duration / 1000)
        if self.recorder:
            self.recorder.record("node", node, duration_ms=duration, payload=payload)

    async def load_context(self, state: CoachState) -> dict:
        started = time.perf_counter()
        conversation = self.db.get(Conversation, state["conversation_id"])
        recent = list(self.db.scalars(
            select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at.desc()).limit(self.settings.context_message_limit)
        ))
        recent.reverse()
        profile = self.memory.get_profile(state["user_id"])
        memories = self.memory.recall(state["user_id"])
        result = {
            "mode": conversation.mode,
            "context_summary": conversation.context_summary,
            "recent_messages": [{"role": item.role, "content": item.content} for item in recent],
            "profile": {
                "industry": profile.industry, "job_title": profile.job_title,
                "cefr_level": profile.cefr_level, "goals": profile.goals,
            },
            "recalled_memories": [
                {"id": item.id, "type": item.memory_type, "content": item.content, "confidence": item.confidence}
                for item in memories
            ],
        }
        self._trace("load_context", started, {"messages": len(recent), "memories": len(memories)})
        return result

    async def understand_request(self, state: CoachState) -> dict:
        started = time.perf_counter()
        intent = infer_intent(state["user_message"], state.get("mode", "coach"))
        plans = {
            "writing": ["identify intent and audience", "rewrite for tone and clarity", "teach one reusable pattern"],
            "roleplay": ["set the business scene", "respond in role", "score and coach the learner"],
            "diagnostic": ["sample core skills", "score with rubric", "create a learning priority"],
            "review": ["recall a weak point", "test without hints", "schedule the next review"],
            "coach": ["clarify the business goal", "offer natural English", "ask for active practice"],
        }
        result = {"intent": intent, "task_plan": plans[intent]}
        self._trace("understand_request", started, result)
        return result

    async def retrieve_context(self, state: CoachState) -> dict:
        started = time.perf_counter()
        embedding = (await self.provider.embed([state["user_message"]]))[0]
        hits = self.knowledge.search(state["user_id"], state["user_message"], embedding)
        result = {
            "knowledge_hits": [hit.__dict__ for hit in hits],
            "citations": [hit.citation for hit in hits],
            "tool_events": [{"tool": "search_knowledge", "status": "ok", "result_count": len(hits)}],
        }
        self._trace("retrieve_context", started, {"hits": len(hits), "tool": "search_knowledge"})
        return result

    async def coach(self, state: CoachState) -> dict:
        started = time.perf_counter()
        last_error = None
        for attempt in range(self.settings.max_tool_retries + 1):
            try:
                result = await asyncio.wait_for(
                    self.provider.complete(build_coach_prompt(state)),
                    timeout=self.settings.tool_timeout_seconds * 3,
                )
                break
            except Exception as exc:
                last_error = exc
                if attempt >= self.settings.max_tool_retries:
                    raise
                await asyncio.sleep(min(2 ** attempt, 4))
                if self.recorder:
                    self.recorder.record("retry", "model.complete", status="retrying", payload={"attempt": attempt + 1, "error_type": type(exc).__name__})
        else:
            raise last_error or RuntimeError("Model call failed")
        MODEL_TOKENS.labels(direction="input").inc(result.input_tokens)
        MODEL_TOKENS.labels(direction="output").inc(result.output_tokens)
        self._trace("coach", started, {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens})
        return {"response": result.content, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens}

    async def assess(self, state: CoachState) -> dict:
        started = time.perf_counter()
        assessment = basic_assessment(state["user_message"])
        candidates = []
        match = re.search(r"(?:I work (?:as|in)|我是|我在)(.{2,80})", state["user_message"], re.IGNORECASE)
        if match:
            candidates.append({"type": "profile", "key": "work-context", "content": match.group(0).strip(), "confidence": 0.85})
        self._trace("assess", started, assessment)
        return {"assessment": assessment, "memory_candidates": candidates}

    async def persist(self, state: CoachState) -> dict:
        started = time.perf_counter()
        user_message = Message(conversation_id=state["conversation_id"], role="user", content=state["user_message"])
        assistant_message = Message(
            conversation_id=state["conversation_id"], role="assistant", content=state["response"],
            metadata_json={"assessment": state["assessment"], "citations": state.get("citations", []), "plan": state["task_plan"]},
        )
        self.db.add_all([user_message, assistant_message])
        self.db.flush()
        for candidate in state.get("memory_candidates", []):
            self.memory.remember(
                state["user_id"], candidate["type"], candidate["content"], key=candidate["key"],
                confidence=candidate["confidence"], source_message_id=user_message.id,
            )
        message_count = self.db.scalar(
            select(func.count()).select_from(Message).where(Message.conversation_id == state["conversation_id"])
        ) or 0
        if message_count > self.settings.context_message_limit:
            conversation = self.db.get(Conversation, state["conversation_id"])
            older = list(self.db.scalars(
                select(Message).where(Message.conversation_id == state["conversation_id"])
                .order_by(Message.created_at)
                .limit(message_count - self.settings.context_message_limit)
            ))
            # A compact extract is intentionally stored separately from source
            # messages. Nothing is deleted, so summaries can be audited/rebuilt.
            conversation.context_summary = " | ".join(
                f"{item.role}: {item.content[:180]}" for item in older[-6:]
            )
        self.db.commit()
        self._trace("persist", started, {"memory_candidates": len(state.get("memory_candidates", []))})
        return {}

    def compile(self, checkpointer=None):
        graph = StateGraph(CoachState)
        graph.add_node("load_context", self.load_context)
        graph.add_node("understand_request", self.understand_request)
        graph.add_node("retrieve_context", self.retrieve_context)
        graph.add_node("coach", self.coach)
        graph.add_node("assess", self.assess)
        graph.add_node("persist", self.persist)
        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "understand_request")
        graph.add_edge("understand_request", "retrieve_context")
        graph.add_edge("retrieve_context", "coach")
        graph.add_edge("coach", "assess")
        graph.add_edge("assess", "persist")
        graph.add_edge("persist", END)
        return graph.compile(checkpointer=checkpointer)

    async def run(self, user_id: str, conversation_id: str, content: str) -> tuple[AgentRun, CoachState]:
        conversation = self.db.get(Conversation, conversation_id)
        if not conversation or conversation.user_id != user_id:
            raise ValueError("Conversation not found")
        run = AgentRun(user_id=user_id, conversation_id=conversation_id)
        self.db.add(run)
        self.db.commit()
        self.recorder = TraceRecorder(self.db, run)
        started = time.perf_counter()
        try:
            async with checkpoint_context() as checkpointer:
                output = await self.compile(checkpointer).ainvoke({
                    "run_id": run.id, "trace_id": run.trace_id, "user_id": user_id,
                    "conversation_id": conversation_id, "user_message": content,
                    "input_tokens": 0, "output_tokens": 0, "tool_events": [],
                }, config={"configurable": {"thread_id": conversation_id, "checkpoint_ns": "coach"}})
            run.status = RunStatus.COMPLETED
            run.input_tokens = output.get("input_tokens", 0)
            run.output_tokens = output.get("output_tokens", 0)
            run.current_node = "end"
            run.completed_at = datetime.now(UTC)
            AGENT_RUNS.labels(status="completed").inc()
        except Exception as exc:
            run.status = RunStatus.FAILED
            run.error_type = type(exc).__name__
            run.error_message = str(exc)[:1000]
            run.completed_at = datetime.now(UTC)
            AGENT_RUNS.labels(status="failed").inc()
            self.db.commit()
            raise
        finally:
            run.latency_ms = int((time.perf_counter() - started) * 1000)
            self.db.commit()
        return run, output
