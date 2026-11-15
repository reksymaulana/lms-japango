from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Bunpou, Kanji, Vocabulary
from app.services.external_api import search_jisho

router = APIRouter(prefix="/learning", tags=["learning"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/kanji", response_class=HTMLResponse)
async def kanji_list(
    request: Request,
    level: str = Query(default="N5", pattern=r"^N[3-5]$"),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    result = await session.scalars(
        select(Kanji).where(Kanji.level == level).order_by(Kanji.character).limit(100)
    )
    return templates.TemplateResponse(
        request=request,
        name="learning/kanji.html",
        context={"kanji_list": result.all(), "level": level},
    )


@router.get("/vocabulary", response_class=HTMLResponse)
async def vocabulary_search(
    request: Request,
    q: str = Query(default="", max_length=100),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    if not q.strip():
        if request.headers.get("HX-Request") != "true":
            return templates.TemplateResponse(
                request=request,
                name="learning/vocabulary.html",
                context={"vocabulary_list": [], "q": ""},
            )
        return templates.TemplateResponse(
            request=request,
            name="partials/vocabulary_results.html",
            context={"vocabulary_list": []},
        )

    query = q.strip()
    cached = await session.scalars(
        select(Vocabulary).where(
            or_(Vocabulary.word == query, Vocabulary.reading == query)
        )
    )
    vocabulary_list = cached.all()
    if not vocabulary_list:
        vocabulary_list = await search_jisho(query)
    for item in vocabulary_list:
        existing = item if isinstance(item, Vocabulary) else await session.scalar(
            select(Vocabulary).where(Vocabulary.word == item.word)
        )
        if existing:
            if not isinstance(item, Vocabulary):
                existing.reading = item.reading
                existing.meanings = item.meanings
        else:
            session.add(
                Vocabulary(
                    word=item.word,
                    reading=item.reading,
                    meanings=item.meanings,
                    jlpt_level=item.jlpt_level,
                )
            )
    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name=(
            "partials/vocabulary_results.html"
            if request.headers.get("HX-Request") == "true"
            else "learning/vocabulary.html"
        ),
        context={"vocabulary_list": vocabulary_list, "q": query},
    )


@router.get("/grammar", response_class=HTMLResponse)
async def grammar_list(
    request: Request,
    level: str = Query(default="N5", pattern=r"^N[3-5]$"),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    result = await session.scalars(
        select(Bunpou).where(Bunpou.level == level).order_by(Bunpou.title)
    )
    return templates.TemplateResponse(
        request=request,
        name="learning/grammar.html",
        context={"grammar_list": result.all(), "level": level},
    )
