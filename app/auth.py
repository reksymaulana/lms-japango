from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit

import jwt
from fastapi import Cookie, Depends, Request
from jwt import (
    PyJWKClient,
    PyJWKClientConnectionError,
    PyJWKClientError,
    PyJWKError,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models import AppUser

SESSION_COOKIE_NAME = "japango_session"


class LoginRequired(Exception):
    pass


class RoleDenied(Exception):
    pass


class AccountDisabled(Exception):
    pass


class AuthUnavailable(Exception):
    pass


class InvalidAuthToken(Exception):
    pass


def _auth_origin() -> str:
    if not settings.neon_auth_base_url:
        raise AuthUnavailable("Neon Auth is not configured")
    parsed = urlsplit(settings.neon_auth_base_url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise AuthUnavailable("NEON_AUTH_BASE_URL must be an absolute URL")
    return f"{parsed.scheme}://{parsed.netloc}"


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    origin = _auth_origin()
    jwks_url = settings.neon_auth_jwks_url or (
        f"{settings.neon_auth_base_url.rstrip('/')}/.well-known/jwks.json"
    )
    return PyJWKClient(jwks_url, cache_keys=True, timeout=5)


async def verify_neon_access_token(token: str) -> dict[str, Any]:
    try:
        origin = _auth_origin()
        signing_key = await asyncio.to_thread(
            _jwks_client().get_signing_key_from_jwt, token
        )
    except AuthUnavailable:
        raise
    except PyJWKClientConnectionError as exc:
        raise AuthUnavailable("Could not retrieve Neon Auth signing keys") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidAuthToken("Neon Auth token is malformed") from exc
    except PyJWKClientError as exc:
        raise InvalidAuthToken("Could not identify Neon Auth signing key") from exc
    except PyJWKError as exc:
        raise InvalidAuthToken("Could not identify Neon Auth signing key") from exc

    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["EdDSA"],
            issuer=origin,
            audience=origin,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.InvalidTokenError as exc:
        raise InvalidAuthToken("Neon Auth token is invalid") from exc

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise InvalidAuthToken("Neon Auth token has an invalid subject")
    if claims.get("role") != "authenticated":
        raise InvalidAuthToken("Neon Auth token is not an authenticated user session")
    if claims.get("banned") is True:
        raise InvalidAuthToken("Neon Auth account is banned")
    return claims


async def get_or_create_account(
    session: AsyncSession, claims: dict[str, Any]
) -> AppUser:
    auth_user_id = claims["sub"]
    account = await session.get(AppUser, auth_user_id)
    if account is None:
        name = claims.get("name")
        email = claims.get("email")
        account = AppUser(
            auth_user_id=auth_user_id,
            name=name[:100] if isinstance(name, str) else None,
            email=email[:320] if isinstance(email, str) else None,
            role="student",
            is_active=True,
        )
        session.add(account)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            account = await session.get(AppUser, auth_user_id)
            if account is None:
                raise
    else:
        name = claims.get("name")
        email = claims.get("email")
        changed = False
        if isinstance(name, str) and account.name != name[:100]:
            account.name = name[:100]
            changed = True
        if isinstance(email, str) and account.email != email[:320]:
            account.email = email[:320]
            changed = True
        if changed:
            await session.commit()
    return account


async def get_current_account(
    request: Request,
    session: AsyncSession = Depends(get_session),
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> AppUser:
    if not session_token:
        raise LoginRequired
    try:
        claims = await verify_neon_access_token(session_token)
    except AuthUnavailable:
        raise
    except InvalidAuthToken as exc:
        raise LoginRequired from exc

    account = await get_or_create_account(session, claims)
    if not account.is_active:
        raise AccountDisabled
    request.state.account = account
    return account


def require_role(role: str):
    async def dependency(
        account: AppUser = Depends(get_current_account),
    ) -> AppUser:
        if account.role != role:
            raise RoleDenied
        return account

    return dependency


async def account_for_token(
    token: str, session: AsyncSession
) -> tuple[AppUser, dict[str, Any]]:
    try:
        claims = await verify_neon_access_token(token)
    except (AuthUnavailable, InvalidAuthToken):
        raise
    account = await get_or_create_account(session, claims)
    if not account.is_active:
        raise AccountDisabled
    return account, claims
