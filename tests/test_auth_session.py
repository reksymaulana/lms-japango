import time
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.auth import InvalidAuthToken, account_for_token, verify_neon_access_token
from app.database import get_session
from app.main import app
from app.models import AppUser


class AccountSession:
    def __init__(self) -> None:
        self.accounts: dict[str, AppUser] = {}
        self.pending: list[AppUser] = []

    async def get(self, model, key):
        return self.accounts.get(key)

    def add(self, account: AppUser) -> None:
        self.pending.append(account)

    async def commit(self) -> None:
        for account in self.pending:
            self.accounts[account.auth_user_id] = account
        self.pending.clear()

    async def rollback(self) -> None:
        self.pending.clear()


class AuthSessionTests(IsolatedAsyncioTestCase):
    async def test_verifies_ed25519_signature_issuer_audience_and_expiry(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        token = jwt.encode(
            {
                "sub": "neon-user-123",
                "role": "authenticated",
                "iss": "https://auth.example.test",
                "aud": "https://auth.example.test",
                "exp": time.time() + 600,
            },
            private_key,
            algorithm="EdDSA",
            headers={"kid": "test-key"},
        )
        jwks_client = SimpleNamespace(
            get_signing_key_from_jwt=lambda _: SimpleNamespace(
                key=private_key.public_key()
            )
        )

        with (
            patch("app.auth.settings.neon_auth_base_url", "https://auth.example.test/app"),
            patch("app.auth._jwks_client", return_value=jwks_client),
        ):
            claims = await verify_neon_access_token(token)

        self.assertEqual(claims["sub"], "neon-user-123")

    async def test_rejects_wrong_audience(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        token = jwt.encode(
            {
                "sub": "neon-user-123",
                "role": "authenticated",
                "iss": "https://auth.example.test",
                "aud": "https://other.example.test",
                "exp": time.time() + 600,
            },
            private_key,
            algorithm="EdDSA",
        )
        jwks_client = SimpleNamespace(
            get_signing_key_from_jwt=lambda _: SimpleNamespace(
                key=private_key.public_key()
            )
        )

        with (
            patch("app.auth.settings.neon_auth_base_url", "https://auth.example.test/app"),
            patch("app.auth._jwks_client", return_value=jwks_client),
        ):
            with self.assertRaises(InvalidAuthToken):
                await verify_neon_access_token(token)

    async def test_rejects_expired_token(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        token = jwt.encode(
            {
                "sub": "neon-user-123",
                "role": "authenticated",
                "iss": "https://auth.example.test",
                "aud": "https://auth.example.test",
                "exp": time.time() - 10,
            },
            private_key,
            algorithm="EdDSA",
        )
        jwks_client = SimpleNamespace(
            get_signing_key_from_jwt=lambda _: SimpleNamespace(
                key=private_key.public_key()
            )
        )

        with (
            patch("app.auth.settings.neon_auth_base_url", "https://auth.example.test/app"),
            patch("app.auth._jwks_client", return_value=jwks_client),
        ):
            with self.assertRaises(InvalidAuthToken):
                await verify_neon_access_token(token)

    async def test_new_account_is_student_even_if_claim_contains_sensei_role(self) -> None:
        session = AccountSession()
        claims = {
            "sub": "neon-user-123",
            "email": "student@example.test",
            "name": "Student",
            "role": "authenticated",
            "app_role": "sensei",
        }
        with patch(
            "app.auth.verify_neon_access_token",
            new_callable=AsyncMock,
            return_value=claims,
        ):
            account, _ = await account_for_token("valid-neon-token", session)

        self.assertEqual(account.auth_user_id, "neon-user-123")
        self.assertEqual(account.role, "student")

    async def test_session_exchange_sets_http_only_cookie_without_returning_token(self) -> None:
        account = AppUser(auth_user_id="neon-user-123", role="student")

        async def override_session():
            yield AccountSession()

        app.dependency_overrides[get_session] = override_session
        self.addCleanup(app.dependency_overrides.pop, get_session, None)

        with patch(
            "app.routers.auth.account_for_token",
            new_callable=AsyncMock,
            return_value=(
                account,
                {"exp": time.time() + 600},
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="https://testserver",
            ) as client:
                response = await client.post(
                    "/auth/session",
                    json={"access_token": "private-token", "role": "sensei"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"role": "student", "redirect_url": "/dashboard"})
        self.assertNotIn("private-token", response.text)
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=lax", cookie)
