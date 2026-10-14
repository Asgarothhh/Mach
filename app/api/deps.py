import os
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.rag.demo_fixtures import ACME_TENANT_ID, MTS_TENANT_ID

# Используем асинхронный драйвер для FastAPI
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://admin:secret@postgres:5432/voice_agent")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

DEMO_ADMIN_SCOPE = (ACME_TENANT_ID, MTS_TENANT_ID)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


class AdminUser(BaseModel):
    username: str
    role: str
    tenant_scope: list[str]


def get_turn_store():
    from app.api import main

    return main.store


async def get_current_admin() -> AdminUser:
    """Demo principal is scoped to the two fixture tenants when ENVIRONMENT=demo."""
    if os.getenv("ENVIRONMENT", "").strip().lower() == "demo":
        return AdminUser(
            username="admin_demo",
            role="support_supervisor",
            tenant_scope=list(DEMO_ADMIN_SCOPE),
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


async def verify_transcript_access(admin: AdminUser = Depends(get_current_admin)):
    """Проверка прав на чтение транскриптов."""
    allowed_roles = ["support_supervisor", "admin", "break_glass"]
    if admin.role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to transcripts")
    return admin
