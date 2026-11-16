from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal, engine
from app.i18n import create_templates
from app.models import Base, Kanji, UserItemProgress, Vocabulary
from app.routers import learning, review
from app.services.grammar_seed import seed_grammar

templates = create_templates(Path(__file__).parent / "templates")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        await seed_grammar(session)
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(learning.router)
app.include_router(review.router)


@app.post("/language")
async def set_language(
    request: Request,
    lang: Literal["id", "en"] = Form(),
    return_to: str = Form(default="/"),
) -> RedirectResponse:
    if (
        not return_to.startswith("/")
        or return_to.startswith("//")
        or any(character in return_to for character in "\r\n\\")
    ):
        return_to = "/"

    response = RedirectResponse(url=return_to, status_code=303)
    response.set_cookie(
        "lang",
        lang,
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return response


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
