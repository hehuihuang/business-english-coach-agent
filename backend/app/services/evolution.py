from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuditLog, BadCase, ImprovementProposal, SystemSetting

DEFAULT_GATES = {
    "minimum_bad_cases": 10,
    "minimum_pass_rate": 0.90,
    "minimum_quality_gain": 0.03,
    "maximum_latency_regression": 0.10,
    "maximum_cost_regression": 0.10,
    "safety_must_pass": True,
}


class EvolutionService:
    """Controls promotion; generation and publication are intentionally separate."""

    def __init__(self, db: Session):
        self.db = db

    def gates(self) -> dict:
        setting = self.db.get(SystemSetting, "evolution_gates")
        return {**DEFAULT_GATES, **(setting.value if setting else {})}

    def generate_candidate(self, actor_id: str) -> ImprovementProposal:
        open_cases = list(self.db.scalars(select(BadCase).where(BadCase.status == "open")))
        if len(open_cases) < self.gates()["minimum_bad_cases"]:
            raise HTTPException(status_code=409, detail={
                "message": "Not enough bad cases for a meaningful proposal",
                "required": self.gates()["minimum_bad_cases"], "available": len(open_cases),
            })
        clusters: dict[str, int] = {}
        for case in open_cases:
            clusters[case.root_cause] = clusters.get(case.root_cause, 0) + 1
        active = self.db.get(SystemSetting, "active_prompt_version")
        base = (active.value if active else {}).get("version", "coach-v1")
        candidate = ImprovementProposal(
            created_by=actor_id,
            proposal_type="routing",
            base_version=base,
            candidate_version=f"candidate-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            changes={
                "bad_case_clusters": clusters,
                "recommendation": "Review the largest root-cause cluster and tighten its routing/rubric before evaluation.",
                "source_case_ids": [case.id for case in open_cases],
            },
            status="draft",
        )
        self.db.add(candidate)
        self.db.add(AuditLog(actor_id=actor_id, action="improvement.generate", resource_type="improvement", resource_id=candidate.id, detail={"clusters": clusters}))
        self.db.commit()
        return candidate

    def approve(self, proposal: ImprovementProposal, reviewer_id: str):
        summary = proposal.evaluation_summary
        gates = self.gates()
        failures = []
        if summary.get("pass_rate", 0) < gates["minimum_pass_rate"]:
            failures.append("pass_rate")
        if gates["safety_must_pass"] and not summary.get("safety_pass", False):
            failures.append("safety")
        if summary.get("quality_gain", 0) < gates["minimum_quality_gain"]:
            failures.append("quality_gain")
        if failures:
            raise HTTPException(status_code=409, detail={"message": "Release gates failed", "gates": failures})
        current = self.db.get(SystemSetting, "active_prompt_version")
        if current:
            current.value = {"version": proposal.candidate_version, "previous": current.value.get("version")}
        else:
            self.db.add(SystemSetting(key="active_prompt_version", value={"version": proposal.candidate_version, "previous": proposal.base_version}))
        proposal.status = "approved"
        proposal.reviewed_by = reviewer_id
        proposal.reviewed_at = datetime.now(UTC)
        self.db.add(AuditLog(
            actor_id=reviewer_id, action="improvement.approve", resource_type="improvement",
            resource_id=proposal.id, detail={"candidate_version": proposal.candidate_version},
        ))
        self.db.commit()
        return proposal

    def rollback(self, reviewer_id: str):
        current = self.db.get(SystemSetting, "active_prompt_version")
        if not current or not current.value.get("previous"):
            raise HTTPException(status_code=409, detail="No previous version to restore")
        previous = current.value["previous"]
        replaced = current.value.get("version")
        current.value = {"version": previous, "previous": replaced}
        self.db.add(AuditLog(
            actor_id=reviewer_id, action="improvement.rollback", resource_type="prompt_version",
            resource_id=previous, detail={"replaced": replaced},
        ))
        self.db.commit()
        return current.value
