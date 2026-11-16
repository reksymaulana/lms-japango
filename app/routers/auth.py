from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    SESSION_COOKIE_NAME,
    AccountDisabled,
    AuthUnavailable,
    InvalidAuthToken,
    account_for_token,
)
from app.database import get_session
from app.schemas import SessionExchangeRequest

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/session")
async def create_app_session(
    payload: SessionExchangeRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    try:
        account, claims = await account_for_token(payload.access_token, session)
    except AuthUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except InvalidAuthToken as exc:
        raise HTTPException(status_code=401, detail="Invalid Neon Auth session") from exc
    except AccountDisabled as exc:
        raise HTTPException(status_code=403, detail="Account is disabled") from exc

    expires_at = claims["exp"]
    max_age = max(0, int(expires_at - datetime.now(timezone.utc).timestamp()))
    response = JSONResponse(
        {
            "role": account.role,
            "redirect_url": "/dashboard",
        },
        headers={"Cache-Control": "no-store"},
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=payload.access_token,
        max_age=max_age,
        httponly=True,
        secure=(
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto") == "https"
        ),
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=(
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto") == "https"
        ),
        samesite="lax",
        path="/",
    )
    return response
