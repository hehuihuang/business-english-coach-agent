import pytest
from fastapi import HTTPException

from app.models import EvaluationRun, GoldenCase, ImprovementProposal, User
from app.security import hash_password
from app.services.evaluation import EvaluationService, deterministic_metrics
from app.services.evolution import EvolutionService


def admin(db):
    user = User(email="admin@example.com", display_name="Admin", role="admin", password_hash=hash_password("long-password"))
    db.add(user); db.commit(); return user


@pytest.mark.asyncio
async def test_evaluation_creates_results_and_summary(db):
    user = admin(db)
    case = GoldenCase(id="case-1", category="writing", input_text="Improve: send it soon", expected={"contains_any": ["Could"]})
    run = EvaluationRun(created_by=user.id)
    db.add_all([case, run]); db.commit()
    await EvaluationService(db).run(run)
    assert run.status == "completed"
    assert run.summary["cases"] == 1


def test_release_gate_requires_evidence_and_supports_rollback(db):
    user = admin(db)
    proposal = ImprovementProposal(
        created_by=user.id, proposal_type="prompt", base_version="coach-v1", candidate_version="coach-v2",
        changes={"prompt": "better"}, evaluation_summary={"pass_rate": .95, "safety_pass": True, "quality_gain": .05},
    )
    db.add(proposal); db.commit()
    approved = EvolutionService(db).approve(proposal, user.id)
    assert approved.status == "approved"
    assert EvolutionService(db).rollback(user.id)["version"] == "coach-v1"


def test_release_gate_blocks_unsafe_candidate(db):
    user = admin(db)
    proposal = ImprovementProposal(
        proposal_type="prompt", base_version="v1", candidate_version="bad-v2", changes={},
        evaluation_summary={"pass_rate": 1, "safety_pass": False, "quality_gain": .5},
    )
    db.add(proposal); db.commit()
    with pytest.raises(HTTPException):
        EvolutionService(db).approve(proposal, user.id)


def test_deterministic_citation_gate():
    case = GoldenCase(id="citation", category="rag", input_text="cite", expected={"requires_citation": True})
    assert not deterministic_metrics(case, "No source here")["citation_ok"]
    assert deterministic_metrics(case, "Use a deadline [Notes · §1]")["citation_ok"]
