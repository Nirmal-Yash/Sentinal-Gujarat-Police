import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://sentinel:sentinelpass@localhost:5432/sentinel")
ASYNC_URL    = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine  = create_async_engine(ASYNC_URL, echo=False, pool_size=10, max_overflow=20)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with Session() as session:
        yield session
