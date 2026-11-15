from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Kanji, UserItemProgress, Vocabulary
from app.schemas import ReviewAnswer
from app.services.srs_service import calculate_next_review

router = APIRouter(prefix="/review", tags=["review"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


async def _next_card(session: AsyncSession, learner_id: str) -> dict[str, str] | None:
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
        if item_type == "kanji":
            back = "、".join(item.meanings) or "Belum ada arti"
            pronunciation = item.kunyomi[0] if item.kunyomi else item.onyomi[0] if item.onyomi else item.character
            return {
                "item_type": item_type,
                "item_id": item.character,
                "front": item.character,
                "back": back,
                "pronunciation": pronunciation,
            }
        return {
            "item_type": item_type,
            "item_id": item.word,
            "front": item.word,
            "back": "、".join(item.meanings) or "Belum ada arti",
            "pronunciation": item.reading or item.word,
        }
    return None


@router.get("", response_class=HTMLResponse)
async def review_page(
    request: Request,
    learner_id: str = "demo",
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    card = await _next_card(session, learner_id)
    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context={"card": card, "learner_id": learner_id},
    )


@router.post("/answer", response_class=HTMLResponse)
async def submit_answer(
    request: Request,
    learner_id: str = Form(default="demo", min_length=1, max_length=100),
    item_type: str = Form(),
    item_id: str = Form(min_length=1, max_length=255),
    quality: int = Form(ge=0, le=5),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    answer = ReviewAnswer(
        learner_id=learner_id,
        item_type=item_type,
        item_id=item_id,
        quality=quality,
    )
    progress = await session.scalar(
        select(UserItemProgress).where(
            UserItemProgress.learner_id == answer.learner_id,
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
            learner_id=answer.learner_id,
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

    card = await _next_card(session, answer.learner_id)
    return templates.TemplateResponse(
        request=request,
        name="partials/flashcard.html",
        context={"card": card, "learner_id": answer.learner_id, "answered": True},
    )
