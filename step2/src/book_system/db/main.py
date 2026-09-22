from sqlmodel import SQLModel, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine
from book_system.config import config

engine = AsyncEngine(create_engine(
    url = config.DATABASE_URL,
    echo = True
))

async def init_db():
    async with engine.begin() as conn:
        from book_system.model.main import Book
        await conn.run_sync(SQLModel.metadata.create_all)