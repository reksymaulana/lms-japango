from math import ceil
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_account, require_role
from app.database import get_session
from app.i18n import GRAMMAR_ENGLISH, create_templates, get_language
from app.models import (
    AppUser,
    Bunpou,
    GrammarProgress,
    GrammarQuizAssignment,
    Kanji,
    Quiz,
    Vocabulary,
)
from app.services.external_api import search_jisho
from app.services.grammar_progress import completed_grammar_ids
from app.services.translation_service import translate_meaning_groups

router = APIRouter(
    prefix="/learning",
    tags=["learning"],
    dependencies=[Depends(get_current_account)],
)
templates = create_templates(Path(__file__).resolve().parents[1] / "templates")
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
    kanji_list = result.all()
    language = get_language(request)
    localized_meanings, translation_unavailable = await translate_meaning_groups(
        session,
        {kanji.character: kanji.meanings for kanji in kanji_list},
        language,
    )
    if language == "id":
        await session.commit()
    context = {
        "kanji_list": kanji_list,
        "localized_meanings": localized_meanings,
        "translation_unavailable": translation_unavailable,
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
        saved_vocabulary_list = result.all()
        language = get_language(request)
        localized_meanings, translation_unavailable = await translate_meaning_groups(
            session,
            {item.word: item.meanings for item in saved_vocabulary_list},
            language,
        )
        if language == "id":
            await session.commit()
        context = {
            "q": "",
            "page": page,
            "pages": pages,
            "total": total,
            "first_item": (page - 1) * PAGE_SIZE + 1 if total else 0,
            "last_item": min(page * PAGE_SIZE, total),
            "saved_vocabulary_list": saved_vocabulary_list,
            "localized_meanings": localized_meanings,
            "translation_unavailable": translation_unavailable,
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

    language = get_language(request)
    localized_meanings, translation_unavailable = await translate_meaning_groups(
        session,
        {item.word: item.meanings for item in vocabulary_list},
        language,
    )
    if language == "id":
        await session.commit()

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
            "localized_meanings": localized_meanings,
            "translation_unavailable": translation_unavailable,
        },
    )


@router.get("/grammar", response_class=HTMLResponse)
async def grammar_list(
    request: Request,
    level: str = Query(default="N5", pattern=r"^N[3-5]$"),
    q: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    account: AppUser = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    filters = [Bunpou.level == level]
    query = q.strip()
    if query:
        pattern = f"%{query}%"
        english_titles = [
            title
            for title, content in GRAMMAR_ENGLISH.items()
            if get_language(request) == "en"
            and query.casefold()
            in " ".join(
                [
                    content["title"],
                    content["explanation"],
                    *content["examples"].values(),
                ]
            ).casefold()
        ]
        filters.append(
            or_(
                Bunpou.title.ilike(pattern),
                Bunpou.explanation.ilike(pattern),
                cast(Bunpou.examples, String).ilike(pattern),
                *([Bunpou.title.in_(english_titles)] if english_titles else []),
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
    grammar_list = result.all()
    completed_ids = await completed_grammar_ids(
        session,
        account.auth_user_id,
        [grammar.id for grammar in grammar_list],
    )
    linked_quizzes: dict[int, list[Quiz]] = {}
    if grammar_list:
        quiz_rows = await session.execute(
            select(GrammarQuizAssignment.grammar_id, Quiz)
            .join(Quiz, Quiz.id == GrammarQuizAssignment.quiz_id)
            .where(
                GrammarQuizAssignment.grammar_id.in_(
                    [grammar.id for grammar in grammar_list]
                ),
                Quiz.published.is_(True),
            )
            .order_by(Quiz.title)
        )
        for grammar_id, quiz in quiz_rows.all():
            linked_quizzes.setdefault(grammar_id, []).append(quiz)
    context = {
        "grammar_list": grammar_list,
        "completed_grammar_ids": completed_ids,
        "linked_quizzes": linked_quizzes,
        "account": account,
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


@router.post("/grammar/{grammar_id}/complete")
async def complete_grammar(
    grammar_id: int,
    level: str = Form(pattern=r"^N[3-5]$"),
    q: str = Form(default="", max_length=100),
    page: int = Form(default=1, ge=1),
    account: AppUser = Depends(require_role("student")),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    grammar = await session.get(Bunpou, grammar_id)
    if grammar is None:
        raise HTTPException(status_code=404, detail="Grammar item not found")
    if grammar.level != level:
        raise HTTPException(status_code=422, detail="Grammar level does not match")

    progress = await session.get(
        GrammarProgress,
        (account.auth_user_id, grammar_id),
    )
    if progress is None:
        session.add(
            GrammarProgress(
                learner_id=account.auth_user_id,
                grammar_id=grammar_id,
            )
        )
        await session.commit()

    query = urlencode({"level": level, "q": q, "page": page})
    return RedirectResponse(f"/learning/grammar?{query}", status_code=303)
