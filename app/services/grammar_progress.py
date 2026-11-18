from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    GrammarProgress,
    GrammarQuizAssignment,
    QuizAttempt,
)

GRAMMAR_PASSING_PERCENT = 70


async def completed_grammar_ids(
    session: AsyncSession,
    learner_id: str,
    grammar_ids: list[int],
) -> set[int]:
    if not grammar_ids:
        return set()

    manual_completions = select(GrammarProgress.grammar_id).where(
        GrammarProgress.learner_id == learner_id,
        GrammarProgress.grammar_id.in_(grammar_ids),
    )
    quiz_completions = (
        select(GrammarQuizAssignment.grammar_id)
        .join(
            QuizAttempt,
            QuizAttempt.quiz_id == GrammarQuizAssignment.quiz_id,
        )
        .where(
            GrammarQuizAssignment.grammar_id.in_(grammar_ids),
            QuizAttempt.student_id == learner_id,
            QuizAttempt.status == "graded",
            QuizAttempt.score * 100
            >= QuizAttempt.max_score * GRAMMAR_PASSING_PERCENT,
        )
    )
    completed_ids = await session.scalars(manual_completions.union(quiz_completions))
    return set(completed_ids.all())
