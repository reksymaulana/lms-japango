from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_account
from app.database import get_session
from app.i18n import TRANSLATIONS, create_templates, get_language
from app.models import AppUser, Kanji, UserItemProgress, Vocabulary
from app.schemas import ReviewAnswer
from app.services.srs_service import calculate_next_review
from app.services.translation_service import translate_meaning_groups

router = APIRouter(prefix="/review", tags=["review"])
templates = create_templates(Path(__file__).resolve().parents[1] / "templates")


async def _next_card(
    session: AsyncSession,
    learner_id: str,
    language: str,
) -> tuple[dict[str, str] | None, bool]:
    now = datetime.now(timezone.utc)
    for item_type, model, item_id_column in (
        ("kanji", Kanji, Kanji.character),
        ("vocabulary", Vocabulary, Vocabulary.word),
    ):
        progress_join = and_(
            UserItemProgress.item_type == item_type,
            UserItemProgress.item_id == item_id_column,
            UserItemProgress.learner_id == learner_id,
        )
        item = await session.scalar(
            select(model)
            .outerjoin(UserItemProgress, progress_join)
            .where(or_(UserItemProgress.id.is_(None), UserItemProgress.due_at <= now))
            .order_by(UserItemProgress.due_at.asc().nullsfirst(), item_id_column.asc())
            .limit(1)
        )
        if item is None:
            continue
        item_key = item.character if item_type == "kanji" else item.word
        localized_meanings, translation_unavailable = await translate_meaning_groups(
            session,
            {item_key: item.meanings},
            language,
        )
        if language == "id":
            await session.commit()
        back = (
            localized_meanings.get(item_key)
            or "、".join(item.meanings)
            or TRANSLATIONS[language]["not_available"]
        )
        if item_type == "kanji":
            pronunciation = item.kunyomi[0] if item.kunyomi else item.onyomi[0] if item.onyomi else item.character
            return (
                {
                    "item_type": item_type,
                    "item_id": item.character,
                    "front": item.character,
                    "back": back,
                    "pronunciation": pronunciation,
                },
                translation_unavailable,
            )
        return (
            {
                "item_type": item_type,
                "item_id": item.word,
                "front": item.word,
                "back": back,
                "pronunciation": item.reading or item.word,
            },
            translation_unavailable,
        )
    return None, False


@router.get("", response_class=HTMLResponse)
async def review_page(
    request: Request,
    account: AppUser = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    card, translation_unavailable = await _next_card(
        session,
        account.auth_user_id,
        get_language(request),
    )
    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context={
            "card": card,
            "translation_unavailable": translation_unavailable,
        },
    )


@router.post("/answer", response_class=HTMLResponse)
async def submit_answer(
    request: Request,
    item_type: str = Form(),
    item_id: str = Form(min_length=1, max_length=255),
    quality: int = Form(ge=0, le=5),
    account: AppUser = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    answer = ReviewAnswer(
        item_type=item_type,
        item_id=item_id,
        quality=quality,
    )
    progress = await session.scalar(
        select(UserItemProgress).where(
            UserItemProgress.learner_id == account.auth_user_id,
            UserItemProgress.item_type == answer.item_type,
            UserItemProgress.item_id == answer.item_id,
        )
    )
    if progress is None:
        item_model = Kanji if answer.item_type == "kanji" else Vocabulary
        item_id_column = Kanji.character if answer.item_type == "kanji" else Vocabulary.word
        item_exists = await session.scalar(
            select(item_id_column).select_from(item_model).where(item_id_column == answer.item_id)
        )
        if item_exists is None:
            raise HTTPException(status_code=404, detail="Kartu tidak ditemukan")
        progress = UserItemProgress(
            learner_id=account.auth_user_id,
            item_type=answer.item_type,
            item_id=answer.item_id,
            repetitions=0,
            interval_days=0,
            ease_factor=2.5,
            due_at=datetime.now(timezone.utc),
        )
        session.add(progress)

    result = calculate_next_review(progress, answer.quality)
    progress.repetitions = result.repetitions
    progress.interval_days = result.interval_days
    progress.ease_factor = result.ease_factor
    progress.due_at = result.due_at
    progress.last_reviewed_at = datetime.now(timezone.utc)
    await session.commit()

    card, translation_unavailable = await _next_card(
        session,
        account.auth_user_id,
        get_language(request),
    )
    return templates.TemplateResponse(
        request=request,
        name="partials/flashcard.html",
        context={
            "card": card,
            "answered": True,
            "translation_unavailable": translation_unavailable,
        },
    )
