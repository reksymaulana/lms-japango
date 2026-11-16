from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_role
from app.database import get_session
from app.i18n import create_templates
from app.models import (
    AppUser,
    Bunpou,
    Kanji,
    LearningMaterial,
    Quiz,
    QuizAttempt,
    UserItemProgress,
    Vocabulary,
)

router = APIRouter(tags=["dashboards"])
templates = create_templates(Path(__file__).resolve().parents[1] / "templates")


@router.get("/student", response_class=HTMLResponse)
async def student_dashboard(
    request: Request,
    account: AppUser = Depends(require_role("student")),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    reviewed_count = await session.scalar(
        select(func.count())
        .select_from(UserItemProgress)
        .where(
            UserItemProgress.learner_id == account.auth_user_id,
            UserItemProgress.last_reviewed_at.is_not(None),
        )
    ) or 0
    kanji_count = await session.scalar(select(func.count()).select_from(Kanji)) or 0
    vocabulary_count = await session.scalar(
        select(func.count()).select_from(Vocabulary)
    ) or 0
    grammar_count = await session.scalar(select(func.count()).select_from(Bunpou)) or 0
    quiz_attempt_count = await session.scalar(
        select(func.count())
        .select_from(QuizAttempt)
        .where(QuizAttempt.student_id == account.auth_user_id)
    ) or 0
    material_count = await session.scalar(
        select(func.count()).select_from(LearningMaterial)
    ) or 0
    quiz_count = await session.scalar(select(func.count()).select_from(Quiz)) or 0
    pending_grade_count = await session.scalar(
        select(func.count())
        .select_from(QuizAttempt)
        .where(QuizAttempt.status == "needs_review")
    ) or 0
    return templates.TemplateResponse(
        request=request,
        name="dashboard/student.html",
        context={
            "account": account,
            "reviewed_count": reviewed_count,
            "learning_counts": {
                "kanji": kanji_count,
                "vocabulary": vocabulary_count,
                "grammar": grammar_count,
            },
            "quiz_attempt_count": quiz_attempt_count,
        },
    )


@router.get("/sensei", response_class=HTMLResponse)
async def sensei_dashboard(
    request: Request,
    account: AppUser = Depends(require_role("sensei")),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    student_count = await session.scalar(
        select(func.count())
        .select_from(AppUser)
        .where(AppUser.role == "student", AppUser.is_active.is_(True))
    ) or 0
    grammar_count = await session.scalar(select(func.count()).select_from(Bunpou)) or 0
    return templates.TemplateResponse(
        request=request,
        name="dashboard/sensei.html",
        context={
            "account": account,
            "student_count": student_count,
            "grammar_count": grammar_count,
            "material_count": material_count,
            "quiz_count": quiz_count,
            "pending_grade_count": pending_grade_count,
        },
    )
