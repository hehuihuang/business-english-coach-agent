from __future__ import annotations

import re
from datetime import UTC, datetime
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent.graph import basic_assessment
from ..models import BadCase, EvaluationResult, EvaluationRun, GoldenCase
from .providers import AIProvider, get_ai_provider

DIMENSIONS = ("grammar", "vocabulary", "tone", "clarity", "business_fit", "teaching_value")


def deterministic_metrics(case: GoldenCase, output: str) -> dict:
    expected_phrases = case.expected.get("contains_any", [])
    phrase_match = not expected_phrases or any(phrase.lower() in output.lower() for phrase in expected_phrases)
    expected_citations = case.expected.get("requires_citation", False)
    citation_ok = not expected_citations or bool(re.search(r"\[[^\]]+· §\d+\]", output))
    prohibited = case.expected.get("prohibited", [])
    safety_ok = not any(item.lower() in output.lower() for item in prohibited)
    return {
        "phrase_match": phrase_match,
        "citation_ok": citation_ok,
        "safety_ok": safety_ok,
        "format_ok": bool(output.strip()),
    }


class EvaluationService:
    def __init__(self, db: Session, provider: AIProvider | None = None):
        self.db = db
        self.provider = provider or get_ai_provider()

    async def run(self, evaluation: EvaluationRun):
        evaluation.status = "running"
        self.db.commit()
        cases = list(self.db.scalars(select(GoldenCase).where(GoldenCase.enabled.is_(True))))
        scores = []
        passes = 0
        for case in cases:
            response = await self.provider.complete([
                {"role": "system", "content": "Act as a Business English coach. Be safe, concise, and pedagogical."},
                {"role": "user", "content": case.input_text},
            ])
            checks = deterministic_metrics(case, response.content)
            heuristic = basic_assessment(response.content)
            score = 100 * sum(bool(value) for value in checks.values()) / len(checks)
            passed = score >= 75 and checks["safety_ok"]
            result = EvaluationResult(
                evaluation_run_id=evaluation.id,
                case_id=case.id,
                passed=passed,
                score=score,
                metrics={**checks, "heuristic": heuristic, "rubric": case.rubric},
                output_text=response.content,
                judge_reason="Deterministic release gate. Human/LLM rubric scores can be attached separately.",
            )
            self.db.add(result)
            self.db.flush()
            scores.append(score)
            passes += int(passed)
            if not passed:
                self.db.add(BadCase(
                    evaluation_result_id=result.id,
                    category=case.category,
                    root_cause="automatic-gate",
                    detail={"checks": checks, "case_id": case.id},
                ))
        evaluation.status = "completed"
        evaluation.completed_at = datetime.now(UTC)
        evaluation.summary = {
            "cases": len(cases), "passed": passes,
            "pass_rate": passes / len(cases) if cases else 0,
            "average_score": mean(scores) if scores else 0,
            "safety_pass": all(item >= 75 for item in scores) if scores else False,
        }
        self.db.commit()
        return evaluation
