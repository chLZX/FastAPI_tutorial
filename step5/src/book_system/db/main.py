from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import sessionmaker
from sqlmodel import create_engine, text, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from book_system.config import Config


async_engine = AsyncEngine(
    create_engine(
        url=Config.DATABASE_URL,
        echo=True,
    )
)


async def init_db() -> None:
    async with async_engine.begin() as conn:
        from book_system.model.main import Book

        await conn.run_sync(
            SQLModel.metadata.create_all
        )


async def get_session():
    Session = sessionmaker(
        bind = async_engine,
        class_ = AsyncSession,
        expire_on_commit = False
    )

    async with Session() as session:
        yield session