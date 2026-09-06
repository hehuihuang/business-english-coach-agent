from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Business English Resources", host="0.0.0.0", port=8010)

TERMS = {
    "align": {"meaning": "reach a shared understanding", "example": "Let's align on the launch criteria."},
    "circle back": {"meaning": "return to a topic later", "example": "I'll circle back after speaking with Finance."},
    "action item": {"meaning": "a concrete task assigned after a discussion", "example": "My action item is to update the forecast."},
    "push back": {"meaning": "challenge or resist a proposal", "example": "Procurement may push back on the price increase."},
}


@mcp.tool()
def business_term_lookup(term: str) -> dict:
    """Look up a business phrase in the curated teaching glossary."""
    item = TERMS.get(term.strip().lower())
    return {"found": bool(item), "term": term, **(item or {"suggestion": "Ask the coach to explain it in context."})}


@mcp.tool()
def company_material_search(query: str, materials: list[str] | None = None) -> dict:
    """Search caller-supplied, already-authorized company snippets.

    The MCP service never opens arbitrary filesystem paths or URLs. A caller must
    first retrieve material through the application's user-scoped knowledge layer.
    """
    materials = materials or []
    terms = query.lower().split()
    matches = [item for item in materials if any(term in item.lower() for term in terms)]
    return {"query": query, "matches": matches[:5], "count": len(matches)}


@mcp.tool()
def practice_schedule(topic: str, due_at_iso: str, confirmed: bool = False) -> dict:
    """Validate a proposed review time; writes require explicit confirmation."""
    if not confirmed:
        return {"status": "confirmation_required", "topic": topic, "due_at": due_at_iso}
    due_at = datetime.fromisoformat(due_at_iso)
    if due_at <= datetime.now(UTC):
        return {"status": "rejected", "reason": "due_at must be in the future"}
    return {"status": "scheduled", "topic": topic, "due_at": due_at.isoformat()}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
