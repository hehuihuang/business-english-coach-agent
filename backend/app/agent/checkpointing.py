from contextlib import asynccontextmanager

from langgraph.checkpoint.memory import InMemorySaver

from ..config import get_settings

_local_checkpointer = InMemorySaver()


@asynccontextmanager
async def checkpoint_context():
    """Select a checkpointer without coupling graph nodes to infrastructure.

    PostgreSQL checkpoints survive API restarts and allow an interrupted graph to
    resume by conversation thread id. SQLite development uses an in-process saver;
    durable chat history still lives in the application tables.
    """
    settings = get_settings()
    if settings.database_url.startswith("postgresql"):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        connection_string = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        async with AsyncPostgresSaver.from_conn_string(connection_string) as saver:
            await saver.setup()
            yield saver
    else:
        yield _local_checkpointer
