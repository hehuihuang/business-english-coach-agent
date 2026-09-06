from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any

from prometheus_client import Counter, Histogram
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AgentRun, TraceEvent

AGENT_RUNS = Counter("coach_agent_runs_total", "Agent runs", ["status"])
MODEL_TOKENS = Counter("coach_model_tokens_total", "Model tokens", ["direction"])
NODE_LATENCY = Histogram("coach_node_duration_seconds", "LangGraph node duration", ["node"])
TOOL_CALLS = Counter("coach_tool_calls_total", "Tool calls", ["tool", "status"])


class TraceRecorder:
    """Writes a compact, user-inspectable trace without leaking raw secrets."""

    def __init__(self, db: Session, run: AgentRun):
        self.db = db
        self.run = run
        self.sequence = db.scalar(select(func.count()).select_from(TraceEvent).where(TraceEvent.run_id == run.id)) or 0

    def record(self, event_type: str, name: str, *, status: str = "ok", duration_ms: int = 0, payload: dict[str, Any] | None = None):
        self.sequence += 1
        safe_payload = {key: value for key, value in (payload or {}).items() if key not in {"api_key", "password", "token"}}
        self.db.add(TraceEvent(
            run_id=self.run.id,
            sequence=self.sequence,
            event_type=event_type,
            name=name,
            status=status,
            duration_ms=duration_ms,
            payload=safe_payload,
        ))
        self.db.commit()

    @contextmanager
    def span(self, event_type: str, name: str, payload: dict[str, Any] | None = None):
        started = time.perf_counter()
        try:
            yield
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            self.record(event_type, name, status="error", duration_ms=duration, payload={"error_type": type(exc).__name__})
            raise
        else:
            duration = int((time.perf_counter() - started) * 1000)
            self.record(event_type, name, duration_ms=duration, payload=payload)
