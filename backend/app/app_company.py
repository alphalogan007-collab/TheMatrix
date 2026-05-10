"""
Company of Minds standalone app — port 8002.
Serves /api/company/*, /mind/company, /api/system/health-matrix + health.
Same Docker image as main backend, different command.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import SQLModel

from app.db.session import engine
from app.routers.company import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    # Start the company report cycle (30 min interval)
    from app.core.company_report_service import start as _start_company_reports
    _start_company_reports()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="MindAI Company",
    description="Company of Minds — CEO dashboard and team health",
    docs_url=None,
    redoc_url=None,
)

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "company", "port": 8002}
