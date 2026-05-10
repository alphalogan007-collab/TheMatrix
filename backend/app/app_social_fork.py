"""
Social Fork standalone app — port 8001.
Serves only /social-fork/* routes + health.
Same Docker image as main backend, different command.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import SQLModel

from app.db.session import engine
from app.routers.social_fork import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="MindAI Social Fork",
    description="Content Creator AI Suite — Social Fork product",
    docs_url=None,
    redoc_url=None,
)

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "social_fork", "port": 8001}
