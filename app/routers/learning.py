from math import ceil
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Bunpou, Kanji, Vocabulary
from app.services.external_api import search_jisho

router = APIRouter(prefix="/learning", tags=["learning"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
PAGE_SIZE = 25
JISHO_PAGE_SIZE = 10


@router.get("/kanji", response_class=HTMLResponse)
async def kanji_list(
    request: Request,
    level: str = Query(default="N5", pattern=r"^N[3-5]$"),
    q: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    filters = [Kanji.level == level]
    query = q.strip()
    if query:
        pattern = f"%{query}%"
        filters.append(
            or_(
                Kanji.character.ilike(pattern),
                cast(Kanji.meanings, String).ilike(pattern),
                cast(Kanji.onyomi, String).ilike(pattern),
                cast(Kanji.kunyomi, String).ilike(pattern),
            )
        )
    total = await session.scalar(
        select(func.count()).select_from(Kanji).where(*filters)
    ) or 0
    pages = max(1, ceil(total / PAGE_SIZE))
    page = min(page, pages)
    result = await session.scalars(
        select(Kanji)
        .where(*filters)
        .order_by(Kanji.character)
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    )
    context = {
        "kanji_list": result.all(),
        "level": level,
        "q": query,
        "page": page,
        "pages": pages,
        "total": total,
        "first_item": (page - 1) * PAGE_SIZE + 1 if total else 0,
        "last_item": min(page * PAGE_SIZE, total),
    }
    return templates.TemplateResponse(
        request=request,
        name=(
            "partials/kanji_results.html"
            if request.headers.get("HX-Request") == "true"
            else "learning/kanji.html"
        ),
        context=context,
    )


@router.get("/vocabulary", response_class=HTMLResponse)
async def vocabulary_search(
    request: Request,
    q: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    if not q.strip():
        total = await session.scalar(select(func.count()).select_from(Vocabulary)) or 0
        pages = max(1, ceil(total / PAGE_SIZE))
        page = min(page, pages)
        result = await session.scalars(
            select(Vocabulary)
            .order_by(Vocabulary.word)
            .offset((page - 1) * PAGE_SIZE)
            .limit(PAGE_SIZE)
        )
        context = {
            "q": "",
            "page": page,
            "pages": pages,
            "total": total,
            "first_item": (page - 1) * PAGE_SIZE + 1 if total else 0,
            "last_item": min(page * PAGE_SIZE, total),
            "saved_vocabulary_list": result.all(),
        }
        if request.headers.get("HX-Request") != "true":
            return templates.TemplateResponse(
                request=request,
                name="learning/vocabulary.html",
                context=context,
            )
        return templates.TemplateResponse(
            request=request,
            name="partials/vocabulary_results.html",
            context=context,
        )

    query = q.strip()
    vocabulary_list = await search_jisho(query, page=page)
    has_next = len(vocabulary_list) == JISHO_PAGE_SIZE

    if vocabulary_list:
        words = [item.word for item in vocabulary_list]
        existing_rows = await session.scalars(
            select(Vocabulary).where(Vocabulary.word.in_(words))
        )
        existing_by_word = {item.word: item for item in existing_rows}
        cached_results = []
        for item in vocabulary_list:
            existing = existing_by_word.get(item.word)
            if existing:
                existing.reading = item.reading
                existing.meanings = item.meanings
                cached_results.append(existing)
            else:
                new_item = Vocabulary(
                    word=item.word,
                    reading=item.reading,
                    meanings=item.meanings,
                    jlpt_level=item.jlpt_level,
                )
                session.add(new_item)
                cached_results.append(new_item)
        await session.commit()
        vocabulary_list = cached_results

    return templates.TemplateResponse(
        request=request,
        name=(
            "partials/vocabulary_results.html"
            if request.headers.get("HX-Request") == "true"
            else "learning/vocabulary.html"
        ),
        context={
            "vocabulary_list": vocabulary_list,
            "q": query,
            "page": page,
            "has_previous": page > 1,
            "has_next": has_next,
        },
    )


@router.get("/grammar", response_class=HTMLResponse)
async def grammar_list(
    request: Request,
    level: str = Query(default="N5", pattern=r"^N[3-5]$"),
    q: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    filters = [Bunpou.level == level]
    query = q.strip()
    if query:
        pattern = f"%{query}%"
        filters.append(
            or_(
                Bunpou.title.ilike(pattern),
                Bunpou.explanation.ilike(pattern),
                cast(Bunpou.examples, String).ilike(pattern),
            )
        )
    total = await session.scalar(
        select(func.count()).select_from(Bunpou).where(*filters)
    ) or 0
    pages = max(1, ceil(total / PAGE_SIZE))
    page = min(page, pages)
    result = await session.scalars(
        select(Bunpou)
        .where(*filters)
        .order_by(Bunpou.title)
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    )
    context = {
        "grammar_list": result.all(),
        "level": level,
        "q": query,
        "page": page,
        "pages": pages,
        "total": total,
        "first_item": (page - 1) * PAGE_SIZE + 1 if total else 0,
        "last_item": min(page * PAGE_SIZE, total),
    }
    return templates.TemplateResponse(
        request=request,
        name=(
            "partials/grammar_results.html"
            if request.headers.get("HX-Request") == "true"
            else "learning/grammar.html"
        ),
        context=context,
    )
