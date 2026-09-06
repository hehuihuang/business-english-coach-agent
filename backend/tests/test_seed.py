import pytest
from sqlalchemy import func, select

from app.models import GoldenCase, KnowledgeDocument
from app.seed import seed_reference_data


@pytest.mark.asyncio
async def test_seed_data_maps_jsonl_contract_and_is_idempotent(db):
    await seed_reference_data(db)
    await seed_reference_data(db)
    assert db.scalar(select(func.count()).select_from(GoldenCase)) == 5
    assert db.scalar(select(func.count()).select_from(KnowledgeDocument)) == 1
