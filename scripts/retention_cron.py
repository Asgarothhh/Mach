import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete
from app.api.deps import AsyncSessionLocal
from app.models.database import Session, Turn, AuditEvent
from app.security.telemetry import get_logger

logger = get_logger("retention_job")

RETENTION_DAYS = 30  # По умолчанию храним 30 дней[cite: 7]


async def clean_old_data():
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    logger.info("starting_retention_cleanup", cutoff_date=cutoff_date.isoformat())

    async with AsyncSessionLocal() as db:
        # Удаляем старые ходы (транскрипты)
        result_turns = await db.execute(delete(Turn).where(Turn.started_at < cutoff_date))
        # Удаляем старые сессии
        result_sessions = await db.execute(delete(Session).where(Session.created_at < cutoff_date))
        # Аудит храним дольше (например, 90 дней), но при необходимости можно удалять и его

        await db.commit()
        logger.info("retention_cleanup_complete",
                    deleted_turns=result_turns.rowcount,
                    deleted_sessions=result_sessions.rowcount)


if __name__ == "__main__":
    asyncio.run(clean_old_data())