from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import httpx

from app.database import get_session
from app.main import app
from app.auth import get_current_account
from app.models import AppUser


LEARNER_ID = "authenticated-student"


class FakeSession:
    def __init__(self, scalar_results: list[object]) -> None:
        self.scalar_results = iter(scalar_results)
        self.added: list[object] = []
        self.committed = False

    async def scalar(self, statement):
        return next(self.scalar_results)

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def commit(self) -> None:
        self.committed = True


class ReviewAuthorizationTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        async def override_session():
            yield self.session

        async def override_account():
            return AppUser(auth_user_id=LEARNER_ID, role="student")

        self.session = FakeSession([])
        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_current_account] = override_account
        self.addCleanup(app.dependency_overrides.pop, get_session, None)
        self.addCleanup(app.dependency_overrides.pop, get_current_account, None)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_review_page_uses_authenticated_learner_id(self) -> None:
        with patch(
            "app.routers.review._next_card",
            new_callable=AsyncMock,
            return_value=(None, False),
        ) as next_card:
            response = await self.client.get("/review?learner_id=another-learner")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(next_card.await_args.args[1], LEARNER_ID)

    async def test_answer_uses_authenticated_learner_id(self) -> None:
        self.session = FakeSession([None, "日"])

        with patch(
            "app.routers.review._next_card",
            new_callable=AsyncMock,
            return_value=(None, False),
        ) as next_card:
            response = await self.client.post(
                "/review/answer",
                data={
                    "learner_id": "another-learner",
                    "item_type": "kanji",
                    "item_id": "日",
                    "quality": "3",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.session.added), 1)
        self.assertEqual(self.session.added[0].learner_id, LEARNER_ID)
        self.assertTrue(self.session.committed)
        self.assertEqual(next_card.await_args.args[1], LEARNER_ID)

    async def test_sensei_cannot_access_student_review_or_submit_answers(self) -> None:
        async def override_sensei():
            return AppUser(auth_user_id="sensei-account", role="sensei")

        app.dependency_overrides[get_current_account] = override_sensei

        review_page = await self.client.get("/review")
        answer_submission = await self.client.post(
            "/review/answer",
            data={"item_type": "kanji", "item_id": "日", "quality": "3"},
        )

        for response in (review_page, answer_submission):
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/dashboard")
        self.assertEqual(self.session.added, [])
        self.assertFalse(self.session.committed)
