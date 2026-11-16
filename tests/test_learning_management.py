from unittest import IsolatedAsyncioTestCase

import httpx

from app.auth import get_current_account
from app.database import get_session
from app.main import app
from app.models import (
    AppUser,
    Bunpou,
    LearningMaterial,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizQuestion,
)


STUDENT = AppUser(auth_user_id="student-1", role="student")
SENSEI = AppUser(auth_user_id="sensei-1", role="sensei")


class FakeResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class LearningSession:
    def __init__(self, *, objects=None, scalar_rows=None, rows=None):
        self.objects = objects or {}
        self.scalar_rows = list(scalar_rows or [])
        self.rows = rows or []
        self.added = []
        self.committed = False

    async def get(self, model, key):
        return self.objects.get((model, key))

    async def scalars(self, statement):
        return FakeResult(self.scalar_rows.pop(0))

    async def scalar(self, statement):
        return self.scalar_rows.pop(0)

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        for item in self.added:
            if isinstance(item, QuizAttempt) and item.id is None:
                item.id = 42

    async def commit(self):
        self.committed = True

    async def execute(self, statement):
        return FakeResult(self.rows)


class LearningManagementTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.session = LearningSession()

        async def override_session():
            yield self.session

        self.session_override = override_session
        app.dependency_overrides[get_session] = override_session
        self.addCleanup(app.dependency_overrides.pop, get_session, None)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )
        self.addAsyncCleanup(self.client.aclose)

    async def use_account(self, account: AppUser) -> None:
        async def override_account():
            return account

        app.dependency_overrides[get_current_account] = override_account
        self.addCleanup(app.dependency_overrides.pop, get_current_account, None)

    async def test_sensei_can_create_learning_material(self) -> None:
        await self.use_account(SENSEI)

        response = await self.client.post(
            "/sensei/materials",
            data={
                "title": "Particles",
                "summary": "Basic particles",
                "content": "は marks the topic.",
                "published": "true",
            },
        )

        self.assertEqual(response.status_code, 303)
        material = next(
            item for item in self.session.added if isinstance(item, LearningMaterial)
        )
        self.assertEqual(material.created_by, SENSEI.auth_user_id)
        self.assertTrue(material.published)
        self.assertTrue(self.session.committed)

    async def test_sensei_can_create_bunpou_grammar(self) -> None:
        await self.use_account(SENSEI)

        response = await self.client.post(
            "/sensei/grammar",
            data={
                "level": "N5",
                "title": "NはNです",
                "explanation": "A basic identity pattern.",
                "examples": "わたしは学生です。 | Saya seorang siswa.",
            },
        )

        self.assertEqual(response.status_code, 303)
        grammar = next(item for item in self.session.added if isinstance(item, Bunpou))
        self.assertEqual(grammar.examples[0]["translation"], "Saya seorang siswa.")

    async def test_sensei_dashboard_renders_management_counts(self) -> None:
        self.session.scalar_rows.extend([4, 3, 2, 1, 1])
        await self.use_account(SENSEI)

        response = await self.client.get("/sensei")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Kelola materi", response.text)
        self.assertIn("Kelola soal", response.text)
        self.assertIn("Jawaban menunggu penilaian", response.text)

    async def test_sensei_can_add_multiple_choice_question(self) -> None:
        self.session.objects[(Quiz, 5)] = Quiz(
            id=5, title="Basics", published=False, created_by="sensei-1"
        )
        self.session.scalar_rows.append(0)
        await self.use_account(SENSEI)

        response = await self.client.post(
            "/sensei/quizzes/5/questions",
            data={
                "prompt": "Choose the topic marker.",
                "question_type": "multiple_choice",
                "options": "は\nが",
                "answer_key": "は",
                "points": "2",
            },
        )

        self.assertEqual(response.status_code, 303)
        question = next(
            item for item in self.session.added if isinstance(item, QuizQuestion)
        )
        self.assertEqual(question.options, ["は", "が"])
        self.assertEqual(question.answer_key, "は")
        self.assertEqual(question.position, 1)

    async def test_student_cannot_create_sensei_material(self) -> None:
        await self.use_account(STUDENT)

        response = await self.client.post(
            "/sensei/materials",
            data={"title": "No access", "content": "Not allowed"},
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/dashboard")
        self.assertEqual(self.session.added, [])

    async def test_quiz_submission_autogrades_choices_and_marks_written_answers_pending(self) -> None:
        quiz = Quiz(id=5, title="Basics", published=True, created_by="sensei-1")
        questions = [
            QuizQuestion(
                id=10,
                quiz_id=5,
                position=1,
                prompt="Which is correct?",
                question_type="multiple_choice",
                options=["A", "B"],
                answer_key="B",
                points=2,
            ),
            QuizQuestion(
                id=11,
                quiz_id=5,
                position=2,
                prompt="Write a sentence.",
                question_type="written",
                options=[],
                answer_key="Use です.",
                points=3,
            ),
        ]
        self.session.objects[(Quiz, 5)] = quiz
        self.session.scalar_rows.append(questions)
        await self.use_account(STUDENT)

        response = await self.client.post(
            "/student/quizzes/5/submit",
            data={"question_10": "B", "question_11": "これは本です。"},
        )

        self.assertEqual(response.status_code, 303)
        attempt = next(
            item for item in self.session.added if isinstance(item, QuizAttempt)
        )
        answers = [item for item in self.session.added if isinstance(item, QuizAnswer)]
        self.assertEqual(attempt.score, 2)
        self.assertEqual(attempt.max_score, 5)
        self.assertEqual(attempt.status, "needs_review")
        self.assertEqual(answers[0].is_correct, True)
        self.assertIsNone(answers[1].score)
        self.assertTrue(self.session.committed)

    async def test_student_cannot_view_another_students_attempt(self) -> None:
        self.session.objects[(QuizAttempt, 99)] = QuizAttempt(
            id=99,
            quiz_id=5,
            student_id="another-student",
            status="graded",
            score=1,
            max_score=1,
        )
        await self.use_account(STUDENT)

        response = await self.client.get("/student/attempts/99")

        self.assertEqual(response.status_code, 404)

    async def test_student_cannot_open_unpublished_material_by_url(self) -> None:
        self.session.objects[(LearningMaterial, 3)] = LearningMaterial(
            id=3,
            created_by="sensei-1",
            title="Draft",
            summary="",
            content="Not public.",
            published=False,
        )
        await self.use_account(STUDENT)

        response = await self.client.get("/student/materials/3")

        self.assertEqual(response.status_code, 404)

    async def test_student_quiz_page_does_not_render_answer_key(self) -> None:
        self.session.objects[(Quiz, 5)] = Quiz(
            id=5, title="Basics", published=True, created_by="sensei-1"
        )
        self.session.scalar_rows.append(
            [
                QuizQuestion(
                    id=10,
                    quiz_id=5,
                    position=1,
                    prompt="Choose one.",
                    question_type="multiple_choice",
                    options=["A", "B"],
                    answer_key="SECRET-ANSWER",
                    points=1,
                )
            ]
        )
        await self.use_account(STUDENT)

        response = await self.client.get("/student/quizzes/5")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Choose one.", response.text)
        self.assertNotIn("SECRET-ANSWER", response.text)

    async def test_sensei_can_grade_written_answer_and_complete_attempt(self) -> None:
        attempt = QuizAttempt(
            id=7,
            quiz_id=5,
            student_id="student-1",
            status="needs_review",
            score=1,
            max_score=4,
        )
        written_question = QuizQuestion(
            id=10,
            quiz_id=5,
            position=1,
            prompt="Write a sentence.",
            question_type="written",
            options=[],
            answer_key="Use です.",
            points=3,
        )
        choice_question = QuizQuestion(
            id=11,
            quiz_id=5,
            position=2,
            prompt="Choose the answer.",
            question_type="multiple_choice",
            options=["A", "B"],
            answer_key="B",
            points=1,
        )
        written_answer = QuizAnswer(
            id=20,
            attempt_id=7,
            question_id=10,
            response="これは本です。",
            score=None,
        )
        choice_answer = QuizAnswer(
            id=21,
            attempt_id=7,
            question_id=11,
            response="B",
            score=1,
        )
        self.session.objects.update(
            {
                (QuizAttempt, 7): attempt,
                (QuizAnswer, 20): written_answer,
                (QuizQuestion, 10): written_question,
            }
        )
        self.session.rows = [
            (written_answer, written_question),
            (choice_answer, choice_question),
        ]
        await self.use_account(SENSEI)

        response = await self.client.post(
            "/sensei/attempts/7/answers/20/grade",
            data={"score": "3", "feedback": "Good sentence."},
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(written_answer.score, 3)
        self.assertEqual(written_answer.feedback, "Good sentence.")
        self.assertEqual(attempt.score, 4)
        self.assertEqual(attempt.status, "graded")
