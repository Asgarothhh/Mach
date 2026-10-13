from typing import AsyncGenerator
from pydantic import BaseModel
from fastapi import Depends, Request
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
import os

# Используем асинхронный драйвер для FastAPI
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://admin:secret@postgres:5432/voice_agent")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

class AdminUser(BaseModel):
    username: str
    role: str
    tenant_id: str

async def get_current_admin() -> AdminUser:
    """
    Заглушка авторизации администратора.
    В продакшене здесь будет проверка JWT и извлечение роли.
    """
    # Хардкод для демо: отдаем пользователя с ролью support_supervisor
    return AdminUser(username="admin_demo", role="support_supervisor", tenant_id="demo-tenant-1")

async def verify_transcript_access(admin: AdminUser = Depends(get_current_admin)):
    """Проверка прав на чтение транскриптов."""
    allowed_roles = ["support_supervisor", "admin", "break_glass"]
    if admin.role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to transcripts")
    return admin