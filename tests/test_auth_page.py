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

