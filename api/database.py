import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://sentinel:sentinelpass@localhost:5432/sentinel")
ASYNC_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
DB_SSL = os.getenv("DB_SSL", "0").lower() in {"1", "true", "yes", "require"}
connect_args = {"server_settings": {"application_name": os.getenv("DB_APPLICATION_NAME", "sentinel_api"), "statement_timeout": str(max(1000, int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "30000")))), "lock_timeout": str(max(1000, int(os.getenv("DB_LOCK_TIMEOUT_MS", "10000"))))}}
if DB_SSL:
    connect_args["ssl"] = "require"
engine = create_async_engine(ASYNC_URL, echo=False, pool_size=max(1, int(os.getenv("DB_POOL_SIZE", "10"))), max_overflow=max(0, int(os.getenv("DB_MAX_OVERFLOW", "20"))), pool_timeout=max(5, int(os.getenv("DB_POOL_TIMEOUT", "30"))), pool_recycle=max(300, int(os.getenv("DB_POOL_RECYCLE", "1800"))), pool_pre_ping=True, connect_args=connect_args)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with Session() as session:
        yield session
