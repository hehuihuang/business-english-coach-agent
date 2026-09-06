from typing import Any, TypedDict


class CoachState(TypedDict, total=False):
    run_id: str
    trace_id: str
    user_id: str
    conversation_id: str
    user_message: str
    mode: str
    intent: str
    task_plan: list[str]
    recent_messages: list[dict[str, str]]
    context_summary: str
    profile: dict[str, Any]
    recalled_memories: list[dict[str, Any]]
    knowledge_hits: list[dict[str, Any]]
    tool_events: list[dict[str, Any]]
    response: str
    assessment: dict[str, Any]
    memory_candidates: list[dict[str, Any]]
    citations: list[str]
    input_tokens: int
    output_tokens: int
    error: str | None
