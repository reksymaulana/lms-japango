from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import httpx

from app.auth import get_current_account, get_optional_current_account
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
        self.assertIn("Login/Register", navigation)
        self.assertNotIn("Akun", navigation)
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
        self.assertIn("<details", student_navigation)
        self.assertIn("Belajar", student_navigation)
        self.assertIn('href="/student/materials"', student_navigation)
        self.assertIn('href="/student/quizzes"', student_navigation)
        self.assertIn('href="/student/history"', student_navigation)
        student_logo = student_navigation.split(
            '<a class="flex min-w-0', 1
        )[1].split(">", 1)[0]
        self.assertIn('href="/student"', student_logo)
        self.assertNotIn("Beranda", student_navigation)
        self.assertNotIn('href="/sensei/materials"', student_navigation)

        sensei_navigation = await render_navigation("sensei")
        self.assertIn("Pengelolaan", sensei_navigation)
        self.assertIn("Akun", sensei_navigation)
        self.assertNotIn("Login/Register", sensei_navigation)
        sensei_logo = sensei_navigation.split(
            '<a class="flex min-w-0', 1
        )[1].split(">", 1)[0]
        self.assertIn('href="/sensei"', sensei_logo)
        self.assertNotIn("Beranda", sensei_navigation)
        self.assertIn('href="/sensei/materials"', sensei_navigation)
        self.assertIn('href="/sensei/quizzes"', sensei_navigation)
        self.assertIn('href="/sensei/students"', sensei_navigation)
        self.assertIn('href="/account"', sensei_navigation)
        self.assertNotIn('href="/student/materials"', sensei_navigation)

    async def test_public_pages_show_the_authenticated_role_navigation(self) -> None:
        from starlette.requests import Request

        from app.models import AppUser

        class EmptyRows:
            def all(self):
                return []

        class EmptySession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            async def execute(self, *_):
                return EmptyRows()

            async def scalar(self, *_):
                return 0

        async def use_role(request: Request, role: str) -> AppUser:
            account = AppUser(auth_user_id=f"{role}-1", role=role)
            request.state.account = account
            return account

        self.addCleanup(
            app.dependency_overrides.pop,
            get_optional_current_account,
            None,
        )
        self.addCleanup(
            app.dependency_overrides.pop,
            get_current_account,
            None,
        )
        with patch("app.main.SessionLocal", side_effect=EmptySession):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                for role, dashboard_path, other_path in (
                    ("student", "/student", "/sensei"),
                    ("sensei", "/sensei", "/student"),
                ):
                    async def authenticated_account(
                        request: Request, role: str = role
                    ) -> AppUser:
                        return await use_role(request, role)

                    app.dependency_overrides[get_optional_current_account] = (
                        authenticated_account
                    )
                    app.dependency_overrides[get_current_account] = (
                        authenticated_account
                    )
                    home = await client.get("/")
                    account_page = await client.get("/account")
                    signup_page = await client.get("/auth/signup")

                    self.assertEqual(home.status_code, 303)
                    self.assertEqual(home.headers["location"], dashboard_path)
                    self.assertEqual(account_page.status_code, 200)
                    self.assertIn("Informasi akun", account_page.text)
                    self.assertNotIn('id="signup-form"', account_page.text)
                    self.assertNotIn('id="signin-form"', account_page.text)
                    self.assertEqual(signup_page.status_code, 303)
                    self.assertEqual(signup_page.headers["location"], "/account")
                    navigation = (
                        account_page.text.split(
                            '<div id="primary-navigation"', 1
                        )[1].split("</div>", 1)[0]
                    )
                    self.assertIn(f'href="{dashboard_path}"', navigation)
                    self.assertNotIn(f'href="{other_path}"', navigation)
                    self.assertIn('href="/account"', account_page.text)
                    self.assertIn(
                        "Siswa" if role == "student" else "Sensei",
                        navigation,
                    )

                async def anonymous_account(request: Request) -> None:
                    request.state.account = None
                    return None

                app.dependency_overrides[get_optional_current_account] = (
                    anonymous_account
                )
                guest_home = await client.get("/")
                self.assertEqual(guest_home.status_code, 200)
                guest_navigation = (
                    guest_home.text.split(
                        '<div id="primary-navigation"', 1
                    )[1].split("</div>", 1)[0]
                )
                self.assertIn('href="/"', guest_navigation)
                self.assertIn('href="/auth/signup"', guest_navigation)

