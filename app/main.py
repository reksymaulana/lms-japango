from contextlib import asynccontextmanager
from pathlib import Path
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal, engine
from app.models import Base, Kanji, UserItemProgress, Vocabulary
from app.routers import learning, review

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(learning.router)
app.include_router(review.router)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    async with SessionLocal() as session:
        kanji_counts = dict(
            (await session.execute(select(Kanji.level, func.count()).group_by(Kanji.level))).all()
        )
        vocabulary_count = await session.scalar(select(func.count()).select_from(Vocabulary)) or 0
        reviewed_count = await session.scalar(
            select(func.count()).select_from(UserItemProgress).where(
                UserItemProgress.learner_id == "demo",
                UserItemProgress.last_reviewed_at.is_not(None),
            )
        ) or 0
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "kanji_counts": kanji_counts,
            "vocabulary_count": vocabulary_count,
            "reviewed_count": reviewed_count,
        },
    )
