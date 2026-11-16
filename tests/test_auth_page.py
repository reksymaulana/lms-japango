from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import httpx

from app.main import app


class AuthPageTests(IsolatedAsyncioTestCase):
    async def test_signup_page_uses_managed_auth_url(self) -> None:
        auth_url = "https://auth.example.test/app"
        with patch("app.main.settings.neon_auth_base_url", auth_url):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                client.cookies.set("lang", "en")
                response = await client.get("/auth/signup")

        self.assertEqual(response.status_code, 200)
        self.assertIn(f'data-auth-base-url="{auth_url}"', response.text)
        self.assertIn("/static/auth.bundle.js", response.text)
        self.assertIn("Create your Japango account", response.text)
        self.assertIn('aria-controls="primary-navigation"', response.text)
        self.assertIn('aria-label="Open navigation menu"', response.text)
        self.assertIn('id="verification-panel"', response.text)
        self.assertIn('id="open-verification"', response.text)
        self.assertIn('name="email"', response.text)
        self.assertIn('name="otp"', response.text)
        self.assertIn("Verification code", response.text)
        navigation = (
            response.text.split('<div id="primary-navigation"', 1)[1]
            .split("</div>", 1)[0]
        )
        self.assertEqual(navigation.count("<a href="), 2)
        self.assertIn('href="/"', navigation)
        self.assertIn('href="/auth/signup"', navigation)
        self.assertNotIn('href="/learning/kanji"', navigation)

    async def test_navigation_is_role_specific(self) -> None:
        from starlette.requests import Request

        from app.main import templates
        from app.models import AppUser

        async def render_navigation(role: str) -> str:
            request = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "scheme": "http",
                    "path": "/",
                    "query_string": b"",
                    "headers": [],
                    "server": ("testserver", 80),
                    "client": ("testclient", 50000),
                    "root_path": "",
                    "http_version": "1.1",
                    "app": app,
                }
            )
            request.state.account = AppUser(auth_user_id=f"{role}-1", role=role)
            response = templates.TemplateResponse(
                request=request,
                name="base.html",
                context={},
            )
            return response.body.decode()

        student_navigation = await render_navigation("student")
        self.assertIn('href="/student/materials"', student_navigation)
        self.assertIn('href="/student/quizzes"', student_navigation)
        self.assertIn('href="/student/history"', student_navigation)
        self.assertNotIn('href="/sensei/materials"', student_navigation)

        sensei_navigation = await render_navigation("sensei")
        self.assertIn('href="/sensei/materials"', sensei_navigation)
        self.assertIn('href="/sensei/quizzes"', sensei_navigation)
        self.assertIn('href="/sensei/students"', sensei_navigation)
        self.assertNotIn('href="/student/materials"', sensei_navigation)

