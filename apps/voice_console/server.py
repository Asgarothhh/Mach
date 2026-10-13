"""Test console for the Stage-1 voice cascade (browser test channel).

Serves the single-page console and bootstraps demo sessions:

* ``GET /``         — the console page (mic -> WS binary PCM16@16k, plays TTS);
* ``POST /session`` — creates a call session via the API and makes sure the
  Tenant/Session rows the orchestrator's Turn FK needs exist in PostgreSQL
  (same workaround as ``scripts/stage1_e2e_smoke.py``; the API on the ``audio``
  branch still keeps sessions in memory only — the backend fix lives on main);
* ``GET /healthz``  — liveness.

The console runs on the demo machine (models included); the VPS Caddy exposes
it publicly and proxies ``/api/*`` to the voice API, so the page talks to the
API through one origin (no CORS/WS fumbling in the browser).

Env:
    VOICE_API_BASE   base URL of the API (default ``http://127.0.0.1:8123``)
    DATABASE_URL     demo stand DB (Tenant/Session rows for the Turn FK)
    VOICE_TENANT_ID  tenant for console sessions (default ``demo-tenant-1``)
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger("voice_console")

HERE = Path(__file__).resolve().parent
API_BASE = os.getenv("VOICE_API_BASE", "http://127.0.0.1:8123")
DATABASE_URL = os.getenv("DATABASE_URL", "")
TENANT_ID = os.getenv("VOICE_TENANT_ID", "demo-tenant-1")

app = FastAPI(title="Voice agent test console")


async def _ensure_db_rows(session_id: str) -> None:
    """Create the Tenant/Session rows the orchestrator's Turn FK needs."""
    if not DATABASE_URL:
        logger.warning("DATABASE_URL is not set: Turn persistence will fail")
        return
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.database import Base, Session, Tenant

    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as db:
            if await db.get(Tenant, TENANT_ID) is None:
                db.add(Tenant(tenant_id=TENANT_ID, display_name="Demo tenant (console)"))
            if await db.get(Session, session_id) is None:
                db.add(
                    Session(
                        session_id=session_id,
                        tenant_id=TENANT_ID,
                        channel="voice-console",
                    )
                )
            await db.commit()
    finally:
        await engine.dispose()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(HERE / "index.html")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/session")
async def create_session() -> dict[str, str]:
    """Create a call session on the API and persist its Tenant/Session rows."""
    try:
        async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
            response = await client.post(
                "/api/v1/sessions",
                json={"tenant_id": TENANT_ID, "channel": "voice-console"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"api_unreachable: {exc}") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"api_error_{response.status_code}")
    session_id = response.json()["session_id"]
    try:
        await _ensure_db_rows(session_id)
    except Exception as exc:  # noqa: BLE001 - best-effort: the call still starts
        logger.error("session rows not created: %r", exc)
    return {"session_id": session_id, "tenant_id": TENANT_ID}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8124)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    logger.info("voice console on http://%s:%d (api: %s)", args.host, args.port, API_BASE)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
