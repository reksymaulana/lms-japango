from unittest import IsolatedAsyncioTestCase

from app.services.grammar_progress import completed_grammar_ids


class ProgressResult:
    def all(self):
        return [4]


class ProgressSession:
    def __init__(self) -> None:
        self.statement = None

    async def scalars(self, statement):
        self.statement = statement
        return ProgressResult()


class GrammarProgressTests(IsolatedAsyncioTestCase):
    async def test_completion_query_combines_manual_and_passing_quiz_progress(self) -> None:
        session = ProgressSession()

        completed = await completed_grammar_ids(session, "student-1", [4, 5])

        self.assertEqual(completed, {4})
        sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("grammar_progress.learner_id = 'student-1'", sql)
        self.assertIn("quiz_attempts.student_id = 'student-1'", sql)
        self.assertIn("quiz_attempts.status = 'graded'", sql)
        self.assertIn(
            "quiz_attempts.score * 100 >= quiz_attempts.max_score * 70",
            sql,
        )

    async def test_empty_grammar_list_skips_completion_query(self) -> None:
        session = ProgressSession()

        completed = await completed_grammar_ids(session, "student-1", [])

        self.assertEqual(completed, set())
        self.assertIsNone(session.statement)
