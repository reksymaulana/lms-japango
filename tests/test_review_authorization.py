from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import httpx

from app.database import get_session
from app.main import app
from app.models import DEMO_LEARNER_ID


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

        self.session = FakeSession([])
        app.dependency_overrides[get_session] = override_session
        self.addCleanup(app.dependency_overrides.pop, get_session, None)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_review_page_ignores_client_supplied_learner_id(self) -> None:
        with patch(
            "app.routers.review._next_card",
            new_callable=AsyncMock,
            return_value=(None, False),
        ) as next_card:
            response = await self.client.get("/review?learner_id=another-learner")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(next_card.await_args.args[1], DEMO_LEARNER_ID)

    async def test_answer_uses_server_selected_demo_learner(self) -> None:
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
        self.assertEqual(self.session.added[0].learner_id, DEMO_LEARNER_ID)
        self.assertTrue(self.session.committed)
        self.assertEqual(next_card.await_args.args[1], DEMO_LEARNER_ID)
