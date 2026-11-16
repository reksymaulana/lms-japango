from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_account, require_role
from app.database import get_session
from app.i18n import create_templates
from app.models import (
    AppUser,
    Bunpou,
    LearningCategory,
    LearningMaterial,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizQuestion,
    UserItemProgress,
)
from app.schemas import BunpouData, CategoryData, MaterialData, QuizData, QuizQuestionData

router = APIRouter(
    prefix="/sensei",
    tags=["sensei"],
    dependencies=[Depends(require_role("sensei"))],
)
templates = create_templates(Path(__file__).resolve().parents[1] / "templates")


def _validate(model: type[BaseModel], **values):
    try:
        return model.model_validate(values)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(include_input=False, include_context=False),
        ) from exc


def _parse_category_id(value: str) -> int | None:
    if not value.strip():
        return None
    try:
        category_id = int(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid category") from exc
    if category_id < 1:
        raise HTTPException(status_code=422, detail="Invalid category")
    return category_id


async def _check_category(
    session: AsyncSession, category_id: int | None
) -> None:
    if category_id is not None and await session.get(LearningCategory, category_id) is None:
        raise HTTPException(status_code=422, detail="Category does not exist")


def _parse_examples(value: str) -> list[dict[str, str]]:
    examples = []
    for line in value.splitlines():
        if not line.strip():
            continue
        if "|" not in line:
            raise HTTPException(
                status_code=422,
                detail="Examples must use one Japanese sentence and translation separated by |.",
            )
        japanese, translation = line.split("|", 1)
        examples.append(
            {"japanese": japanese.strip(), "translation": translation.strip()}
        )
    return examples


async def _ensure_no_attempts_for_question(
    session: AsyncSession, question_id: int
) -> None:
    answer_id = await session.scalar(
        select(QuizAnswer.id).where(QuizAnswer.question_id == question_id).limit(1)
    )
    if answer_id is not None:
        raise HTTPException(
            status_code=409,
            detail="Questions with submitted answers cannot be edited or deleted.",
        )


@router.get("/materials", response_class=HTMLResponse)
async def manage_materials(
    request: Request,
    edit_id: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    materials = await session.scalars(
        select(LearningMaterial).order_by(LearningMaterial.created_at.desc())
    )
    categories = await session.scalars(
        select(LearningCategory).order_by(LearningCategory.name)
    )
    edit_material = (
        await session.get(LearningMaterial, edit_id) if edit_id is not None else None
    )
    return templates.TemplateResponse(
        request=request,
        name="sensei/materials.html",
        context={
            "materials": materials.all(),
            "categories": categories.all(),
            "edit_material": edit_material,
            "message": request.query_params.get("message"),
        },
    )


@router.post("/materials")
async def create_material(
    title: str = Form(),
    summary: str = Form(default=""),
    content: str = Form(),
    category_id: str = Form(default=""),
    published: bool = Form(default=False),
    account: AppUser = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    category = _parse_category_id(category_id)
    data = _validate(
        MaterialData,
        title=title,
        summary=summary,
        content=content,
        category_id=category,
    )
    await _check_category(session, data.category_id)
    session.add(
        LearningMaterial(
            **data.model_dump(),
            published=published,
            created_by=account.auth_user_id,
        )
    )
    await session.commit()
    return RedirectResponse("/sensei/materials?message=Material%20created", status_code=303)


@router.post("/materials/{material_id}/edit")
async def update_material(
    material_id: int,
    title: str = Form(),
    summary: str = Form(default=""),
    content: str = Form(),
    category_id: str = Form(default=""),
    published: bool = Form(default=False),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    material = await session.get(LearningMaterial, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    category = _parse_category_id(category_id)
    data = _validate(
        MaterialData,
        title=title,
        summary=summary,
        content=content,
        category_id=category,
    )
    await _check_category(session, data.category_id)
    for key, value in data.model_dump().items():
        setattr(material, key, value)
    material.published = published
    await session.commit()
    return RedirectResponse("/sensei/materials?message=Material%20updated", status_code=303)


@router.post("/materials/{material_id}/delete")
async def delete_material(
    material_id: int,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    material = await session.get(LearningMaterial, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    await session.delete(material)
    await session.commit()
    return RedirectResponse("/sensei/materials?message=Material%20deleted", status_code=303)


@router.get("/categories", response_class=HTMLResponse)
async def manage_categories(
    request: Request,
    edit_id: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    categories = await session.scalars(
        select(LearningCategory).order_by(LearningCategory.name)
    )
    edit_category = (
        await session.get(LearningCategory, edit_id) if edit_id is not None else None
    )
    return templates.TemplateResponse(
        request=request,
        name="sensei/categories.html",
        context={
            "categories": categories.all(),
            "edit_category": edit_category,
            "message": request.query_params.get("message"),
        },
    )


@router.post("/categories")
async def create_category(
    name: str = Form(),
    description: str = Form(default=""),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    data = _validate(CategoryData, name=name, description=description)
    session.add(LearningCategory(**data.model_dump()))
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Category name already exists") from exc
    return RedirectResponse("/sensei/categories?message=Category%20created", status_code=303)


@router.post("/categories/{category_id}/edit")
async def update_category(
    category_id: int,
    name: str = Form(),
    description: str = Form(default=""),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    category = await session.get(LearningCategory, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    data = _validate(CategoryData, name=name, description=description)
    category.name = data.name
    category.description = data.description
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Category name already exists") from exc
    return RedirectResponse("/sensei/categories?message=Category%20updated", status_code=303)


@router.post("/categories/{category_id}/delete")
async def delete_category(
    category_id: int,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    category = await session.get(LearningCategory, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    await session.delete(category)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="Category is assigned to learning content"
        ) from exc
    return RedirectResponse("/sensei/categories?message=Category%20deleted", status_code=303)


@router.get("/grammar", response_class=HTMLResponse)
async def manage_grammar(
    request: Request,
    edit_id: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    grammar = await session.scalars(select(Bunpou).order_by(Bunpou.level, Bunpou.title))
    edit_grammar = await session.get(Bunpou, edit_id) if edit_id is not None else None
    return templates.TemplateResponse(
        request=request,
        name="sensei/grammar.html",
        context={
            "grammar_list": grammar.all(),
            "edit_grammar": edit_grammar,
            "message": request.query_params.get("message"),
        },
    )


@router.post("/grammar")
async def create_grammar(
    level: str = Form(),
    title: str = Form(),
    explanation: str = Form(),
    examples: str = Form(),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    data = _validate(
        BunpouData,
        level=level,
        title=title,
        explanation=explanation,
        examples=_parse_examples(examples),
    )
    session.add(Bunpou(**data.model_dump()))
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Grammar title already exists") from exc
    return RedirectResponse("/sensei/grammar?message=Grammar%20created", status_code=303)


@router.post("/grammar/{grammar_id}/edit")
async def update_grammar(
    grammar_id: int,
    level: str = Form(),
    title: str = Form(),
    explanation: str = Form(),
    examples: str = Form(),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    grammar = await session.get(Bunpou, grammar_id)
    if grammar is None:
        raise HTTPException(status_code=404, detail="Grammar item not found")
    data = _validate(
        BunpouData,
        level=level,
        title=title,
        explanation=explanation,
        examples=_parse_examples(examples),
    )
    for key, value in data.model_dump().items():
        setattr(grammar, key, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Grammar title already exists") from exc
    return RedirectResponse("/sensei/grammar?message=Grammar%20updated", status_code=303)


@router.post("/grammar/{grammar_id}/delete")
async def delete_grammar(
    grammar_id: int,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    grammar = await session.get(Bunpou, grammar_id)
    if grammar is None:
        raise HTTPException(status_code=404, detail="Grammar item not found")
    await session.delete(grammar)
    await session.commit()
    return RedirectResponse("/sensei/grammar?message=Grammar%20deleted", status_code=303)


@router.get("/quizzes", response_class=HTMLResponse)
async def manage_quizzes(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    quizzes = await session.scalars(
        select(Quiz).order_by(Quiz.created_at.desc())
    )
    categories = await session.scalars(
        select(LearningCategory).order_by(LearningCategory.name)
    )
    return templates.TemplateResponse(
        request=request,
        name="sensei/quizzes.html",
        context={
            "quizzes": quizzes.all(),
            "categories": categories.all(),
            "message": request.query_params.get("message"),
        },
    )


@router.post("/quizzes")
async def create_quiz(
    title: str = Form(),
    description: str = Form(default=""),
    category_id: str = Form(default=""),
    account: AppUser = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    data = _validate(
        QuizData,
        title=title,
        description=description,
        category_id=_parse_category_id(category_id),
    )
    await _check_category(session, data.category_id)
    quiz = Quiz(
        **data.model_dump(),
        published=False,
        created_by=account.auth_user_id,
    )
    session.add(quiz)
    await session.commit()
    return RedirectResponse(f"/sensei/quizzes/{quiz.id}", status_code=303)


@router.post("/quizzes/{quiz_id}/delete")
async def delete_quiz(
    quiz_id: int,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    quiz = await session.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    attempt_id = await session.scalar(
        select(QuizAttempt.id).where(QuizAttempt.quiz_id == quiz_id).limit(1)
    )
    if attempt_id is not None:
        raise HTTPException(status_code=409, detail="Quizzes with attempts cannot be deleted")
    await session.delete(quiz)
    await session.commit()
    return RedirectResponse("/sensei/quizzes?message=Quiz%20deleted", status_code=303)


@router.get("/quizzes/{quiz_id}", response_class=HTMLResponse)
async def edit_quiz(
    request: Request,
    quiz_id: int,
    edit_question_id: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    quiz = await session.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    questions = await session.scalars(
        select(QuizQuestion)
        .where(QuizQuestion.quiz_id == quiz_id)
        .order_by(QuizQuestion.position)
    )
    categories = await session.scalars(
        select(LearningCategory).order_by(LearningCategory.name)
    )
    edit_question = (
        await session.get(QuizQuestion, edit_question_id)
        if edit_question_id is not None
        else None
    )
    if edit_question is not None and edit_question.quiz_id != quiz_id:
        raise HTTPException(status_code=404, detail="Question not found")
    return templates.TemplateResponse(
        request=request,
        name="sensei/quiz_edit.html",
        context={
            "quiz": quiz,
            "questions": questions.all(),
            "categories": categories.all(),
            "edit_question": edit_question,
            "message": request.query_params.get("message"),
        },
    )


@router.post("/quizzes/{quiz_id}/edit")
async def update_quiz(
    quiz_id: int,
    title: str = Form(),
    description: str = Form(default=""),
    category_id: str = Form(default=""),
    published: bool = Form(default=False),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    quiz = await session.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    data = _validate(
        QuizData,
        title=title,
        description=description,
        category_id=_parse_category_id(category_id),
    )
    await _check_category(session, data.category_id)
    if published:
        question_count = await session.scalar(
            select(func.count())
            .select_from(QuizQuestion)
            .where(QuizQuestion.quiz_id == quiz_id)
        )
        if not question_count:
            raise HTTPException(
                status_code=422,
                detail="Add at least one question before publishing this quiz.",
            )
    for key, value in data.model_dump().items():
        setattr(quiz, key, value)
    quiz.published = published
    await session.commit()
    return RedirectResponse(f"/sensei/quizzes/{quiz_id}?message=Quiz%20updated", status_code=303)


@router.post("/quizzes/{quiz_id}/questions")
async def create_question(
    quiz_id: int,
    prompt: str = Form(),
    question_type: str = Form(),
    options: str = Form(default=""),
    answer_key: str = Form(),
    points: int = Form(default=1),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    quiz = await session.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    data = _validate(
        QuizQuestionData,
        prompt=prompt,
        question_type=question_type,
        options=options.splitlines(),
        answer_key=answer_key,
        points=points,
    )
    current_position = await session.scalar(
        select(func.max(QuizQuestion.position)).where(QuizQuestion.quiz_id == quiz_id)
    )
    session.add(
        QuizQuestion(
            quiz_id=quiz_id,
            position=(current_position or 0) + 1,
            **data.model_dump(),
        )
    )
    await session.commit()
    return RedirectResponse(f"/sensei/quizzes/{quiz_id}?message=Question%20created", status_code=303)


@router.post("/quizzes/{quiz_id}/questions/{question_id}/edit")
async def update_question(
    quiz_id: int,
    question_id: int,
    prompt: str = Form(),
    question_type: str = Form(),
    options: str = Form(default=""),
    answer_key: str = Form(),
    points: int = Form(default=1),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    question = await session.get(QuizQuestion, question_id)
    if question is None or question.quiz_id != quiz_id:
        raise HTTPException(status_code=404, detail="Question not found")
    await _ensure_no_attempts_for_question(session, question_id)
    data = _validate(
        QuizQuestionData,
        prompt=prompt,
        question_type=question_type,
        options=options.splitlines(),
        answer_key=answer_key,
        points=points,
    )
    for key, value in data.model_dump().items():
        setattr(question, key, value)
    await session.commit()
    return RedirectResponse(f"/sensei/quizzes/{quiz_id}?message=Question%20updated", status_code=303)


@router.post("/quizzes/{quiz_id}/questions/{question_id}/delete")
async def delete_question(
    quiz_id: int,
    question_id: int,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    question = await session.get(QuizQuestion, question_id)
    if question is None or question.quiz_id != quiz_id:
        raise HTTPException(status_code=404, detail="Question not found")
    await _ensure_no_attempts_for_question(session, question_id)
    await session.delete(question)
    await session.commit()
    return RedirectResponse(f"/sensei/quizzes/{quiz_id}?message=Question%20deleted", status_code=303)


@router.get("/students", response_class=HTMLResponse)
async def student_progress(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    rows = await session.execute(
        select(AppUser, func.count(UserItemProgress.id))
        .outerjoin(
            UserItemProgress,
            and_(
                UserItemProgress.learner_id == AppUser.auth_user_id,
                UserItemProgress.last_reviewed_at.is_not(None),
            ),
        )
        .where(AppUser.role == "student", AppUser.is_active.is_(True))
        .group_by(AppUser.auth_user_id)
        .order_by(AppUser.name, AppUser.email)
    )
    students = [
        {"account": account, "reviewed_count": reviewed_count}
        for account, reviewed_count in rows.all()
    ]
    return templates.TemplateResponse(
        request=request,
        name="sensei/students.html",
        context={"students": students},
    )


@router.get("/attempts", response_class=HTMLResponse)
async def list_attempts(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    rows = await session.execute(
        select(QuizAttempt, Quiz, AppUser)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .join(AppUser, AppUser.auth_user_id == QuizAttempt.student_id)
        .order_by(desc(QuizAttempt.submitted_at))
    )
    attempts = [
        {"attempt": attempt, "quiz": quiz, "student": student}
        for attempt, quiz, student in rows.all()
    ]
    return templates.TemplateResponse(
        request=request,
        name="sensei/attempts.html",
        context={"attempts": attempts},
    )


@router.get("/attempts/{attempt_id}", response_class=HTMLResponse)
async def review_attempt(
    request: Request,
    attempt_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    attempt = await session.get(QuizAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")
    quiz = await session.get(Quiz, attempt.quiz_id)
    student = await session.get(AppUser, attempt.student_id)
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
        name="sensei/attempt_detail.html",
        context={
            "attempt": attempt,
            "quiz": quiz,
            "student": student,
            "answers": answers,
        },
    )


@router.post("/attempts/{attempt_id}/answers/{answer_id}/grade")
async def grade_written_answer(
    attempt_id: int,
    answer_id: int,
    score: int = Form(ge=0, le=100),
    feedback: str = Form(default="", max_length=2000),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    attempt = await session.get(QuizAttempt, attempt_id)
    answer = await session.get(QuizAnswer, answer_id)
    if attempt is None or answer is None or answer.attempt_id != attempt_id:
        raise HTTPException(status_code=404, detail="Answer not found")
    question = await session.get(QuizQuestion, answer.question_id)
    if question is None or question.question_type != "written":
        raise HTTPException(status_code=400, detail="Only written answers can be graded")
    if score > question.points:
        raise HTTPException(status_code=422, detail="Score exceeds question points")
    answer.score = score
    answer.is_correct = score == question.points
    answer.feedback = feedback.strip()
    rows = await session.execute(
        select(QuizAnswer, QuizQuestion)
        .join(QuizQuestion, QuizQuestion.id == QuizAnswer.question_id)
        .where(QuizAnswer.attempt_id == attempt_id)
    )
    answers = rows.all()
    attempt.score = sum(answer_row.score or 0 for answer_row, _ in answers)
    attempt.status = (
        "needs_review"
        if any(
            question_row.question_type == "written" and answer_row.score is None
            for answer_row, question_row in answers
        )
        else "graded"
    )
    await session.commit()
    return RedirectResponse(f"/sensei/attempts/{attempt_id}", status_code=303)
