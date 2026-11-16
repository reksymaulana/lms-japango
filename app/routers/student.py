from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_account, require_role
from app.database import get_session
from app.i18n import create_templates
from app.models import (
    AppUser,
    LearningCategory,
    LearningMaterial,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizQuestion,
)

router = APIRouter(
    prefix="/student",
    tags=["student"],
    dependencies=[Depends(require_role("student"))],
)
templates = create_templates(Path(__file__).resolve().parents[1] / "templates")


@router.get("/materials", response_class=HTMLResponse)
async def available_materials(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    rows = await session.execute(
        select(LearningMaterial, LearningCategory)
        .outerjoin(
            LearningCategory,
            LearningCategory.id == LearningMaterial.category_id,
        )
        .where(LearningMaterial.published.is_(True))
        .order_by(LearningMaterial.created_at.desc())
    )
    materials = [
        {"material": material, "category": category}
        for material, category in rows.all()
    ]
    return templates.TemplateResponse(
        request=request,
        name="student/materials.html",
        context={"materials": materials},
    )


@router.get("/materials/{material_id}", response_class=HTMLResponse)
async def read_material(
    request: Request,
    material_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    material = await session.get(LearningMaterial, material_id)
    if material is None or not material.published:
        raise HTTPException(status_code=404, detail="Material not found")
    category = (
        await session.get(LearningCategory, material.category_id)
        if material.category_id is not None
        else None
    )
    return templates.TemplateResponse(
        request=request,
        name="student/material_detail.html",
        context={"material": material, "category": category},
    )


@router.get("/quizzes", response_class=HTMLResponse)
async def available_quizzes(
    request: Request,
    account: AppUser = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    quizzes = await session.scalars(
        select(Quiz)
        .where(Quiz.published.is_(True))
        .order_by(Quiz.created_at.desc())
    )
    attempts = await session.scalars(
        select(QuizAttempt)
        .where(QuizAttempt.student_id == account.auth_user_id)
        .order_by(desc(QuizAttempt.submitted_at))
    )
    latest_attempts: dict[int, QuizAttempt] = {}
    for attempt in attempts:
        latest_attempts.setdefault(attempt.quiz_id, attempt)
    return templates.TemplateResponse(
        request=request,
        name="student/quizzes.html",
        context={"quizzes": quizzes.all(), "latest_attempts": latest_attempts},
    )


@router.get("/history", response_class=HTMLResponse)
async def quiz_history(
    request: Request,
    account: AppUser = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    rows = await session.execute(
        select(QuizAttempt, Quiz)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .where(QuizAttempt.student_id == account.auth_user_id)
        .order_by(desc(QuizAttempt.submitted_at))
    )
    history = [
        {"attempt": attempt, "quiz": quiz}
        for attempt, quiz in rows.all()
    ]
    return templates.TemplateResponse(
        request=request,
        name="student/history.html",
        context={"history": history},
    )


@router.get("/quizzes/{quiz_id}", response_class=HTMLResponse)
async def take_quiz(
    request: Request,
    quiz_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    quiz = await session.get(Quiz, quiz_id)
    if quiz is None or not quiz.published:
        raise HTTPException(status_code=404, detail="Quiz not found")
    questions = await session.scalars(
        select(QuizQuestion)
        .where(QuizQuestion.quiz_id == quiz_id)
        .order_by(QuizQuestion.position)
    )
    safe_questions = [
        {
            "id": question.id,
            "prompt": question.prompt,
            "question_type": question.question_type,
            "options": question.options,
            "points": question.points,
        }
        for question in questions.all()
    ]
    if not safe_questions:
        raise HTTPException(status_code=409, detail="This quiz has no questions yet")
    return templates.TemplateResponse(
        request=request,
        name="student/quiz_take.html",
        context={"quiz": quiz, "questions": safe_questions},
    )


@router.post("/quizzes/{quiz_id}/submit")
async def submit_quiz(
    request: Request,
    quiz_id: int,
    account: AppUser = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    quiz = await session.get(Quiz, quiz_id)
    if quiz is None or not quiz.published:
        raise HTTPException(status_code=404, detail="Quiz not found")
    questions = await session.scalars(
        select(QuizQuestion)
        .where(QuizQuestion.quiz_id == quiz_id)
        .order_by(QuizQuestion.position)
    )
    question_list = questions.all()
    if not question_list:
        raise HTTPException(status_code=409, detail="This quiz has no questions yet")
    form = await request.form()
    validated_answers: list[tuple[QuizQuestion, str, bool | None, int | None]] = []
    max_score = 0
    score = 0
    needs_review = False
    for question in question_list:
        response = str(form.get(f"question_{question.id}", "")).strip()
        if not response or len(response) > 5000:
            raise HTTPException(
                status_code=422,
                detail=f"Answer for question {question.position} is required and must be at most 5000 characters.",
            )
        max_score += question.points
        if question.question_type == "multiple_choice":
            if response not in question.options:
                raise HTTPException(status_code=422, detail="Invalid multiple-choice answer")
            correct = response == question.answer_key
            answer_score = question.points if correct else 0
            score += answer_score
            validated_answers.append((question, response, correct, answer_score))
        else:
            needs_review = True
            validated_answers.append((question, response, None, None))

    attempt = QuizAttempt(
        quiz_id=quiz_id,
        student_id=account.auth_user_id,
        status="needs_review" if needs_review else "graded",
        score=score,
        max_score=max_score,
    )
    session.add(attempt)
    await session.flush()
    for question, response, correct, answer_score in validated_answers:
        session.add(
            QuizAnswer(
                attempt_id=attempt.id,
                question_id=question.id,
                response=response,
                is_correct=correct,
                score=answer_score,
            )
        )
    await session.commit()
    return RedirectResponse(
        f"/student/attempts/{attempt.id}", status_code=303
    )


@router.get("/attempts/{attempt_id}", response_class=HTMLResponse)
async def view_attempt(
    request: Request,
    attempt_id: int,
    account: AppUser = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    attempt = await session.get(QuizAttempt, attempt_id)
    if attempt is None or attempt.student_id != account.auth_user_id:
        raise HTTPException(status_code=404, detail="Attempt not found")
    quiz = await session.get(Quiz, attempt.quiz_id)
    rows = await session.execute(
        select(QuizAnswer, QuizQuestion)
        .join(QuizQuestion, QuizQuestion.id == QuizAnswer.question_id)
        .where(QuizAnswer.attempt_id == attempt_id)
        .order_by(QuizQuestion.position)
    )
    answers = [
        {"answer": answer, "question": question}
        for answer, question in rows.all()
    ]
    return templates.TemplateResponse(
        request=request,
        name="student/quiz_result.html",
        context={"attempt": attempt, "quiz": quiz, "answers": answers},
    )
