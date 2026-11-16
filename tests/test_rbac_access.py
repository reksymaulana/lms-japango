from unittest import IsolatedAsyncioTestCase

import httpx

from app.auth import get_current_account
from app.main import app
from app.models import AppUser


class RbacAccessTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_learning_route_redirects_anonymous_user_to_login(self) -> None:
        response = await self.client.get("/learning/kanji")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/auth/signup?next=%2Flearning%2Fkanji&refresh=1",
        )

    async def test_sensei_dashboard_rejects_student_role(self) -> None:
        async def student_account():
            return AppUser(auth_user_id="student-1", role="student")

        app.dependency_overrides[get_current_account] = student_account
        self.addCleanup(app.dependency_overrides.pop, get_current_account, None)

        response = await self.client.get("/sensei")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/dashboard")

    async def test_dashboard_redirects_by_server_role(self) -> None:
        async def sensei_account():
            return AppUser(auth_user_id="sensei-1", role="sensei")

        app.dependency_overrides[get_current_account] = sensei_account
        self.addCleanup(app.dependency_overrides.pop, get_current_account, None)

        response = await self.client.get("/dashboard")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/sensei")
