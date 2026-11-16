from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from app.auth import (
    AccountDisabled,
    AuthUnavailable,
    LoginRequired,
    RoleDenied,
    get_current_account,
    get_optional_current_account,
)
from app.config import settings
from app.database import SessionLocal, engine
from app.i18n import create_templates
from app.models import AppUser, Base, Bunpou, Kanji, Vocabulary
from app.routers import auth, dashboard, learning, review, sensei, student
from app.services.grammar_seed import seed_grammar

templates = create_templates(Path(__file__).parent / "templates")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        await seed_grammar(session)
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)
app.include_router(learning.router)
app.include_router(review.router)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(sensei.router)
app.include_router(student.router)


@app.exception_handler(LoginRequired)
async def login_required(request: Request, _: LoginRequired) -> Response:
    auth_url = f"/auth/signup?{urlencode({'next': request.url.path, 'refresh': '1'})}"
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=401, headers={"HX-Redirect": auth_url})
    return RedirectResponse(url=auth_url, status_code=303)


@app.exception_handler(RoleDenied)
async def role_denied(request: Request, _: RoleDenied) -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=303)


@app.exception_handler(AccountDisabled)
async def account_disabled(_: Request, __: AccountDisabled) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": "Account is disabled"})


@app.exception_handler(AuthUnavailable)
async def auth_unavailable(_: Request, exc: AuthUnavailable) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get(
    "/auth/signup",
    response_class=HTMLResponse,
    dependencies=[Depends(get_optional_current_account)],
)
async def auth_signup(request: Request) -> HTMLResponse:
    return_to = request.query_params.get("next", "")
    if (
        not return_to.startswith("/")
        or return_to.startswith("//")
        or any(character in return_to for character in "\r\n\\")
    ):
        return_to = ""
    return templates.TemplateResponse(
        request=request,
        name="auth.html",
        context={
            "auth_base_url": settings.neon_auth_base_url,
            "return_to": return_to,
        },
    )


@app.post("/language")
async def set_language(
    request: Request,
    lang: Literal["id", "en"] = Form(),
    return_to: str = Form(default="/"),
) -> RedirectResponse:
    if (
        not return_to.startswith("/")
        or return_to.startswith("//")
        or any(character in return_to for character in "\r\n\\")
    ):
        return_to = "/"

    response = RedirectResponse(url=return_to, status_code=303)
    response.set_cookie(
        "lang",
        lang,
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return response


@app.get("/dashboard")
async def role_dashboard(
    account: AppUser = Depends(get_current_account),
) -> RedirectResponse:
    destination = "/sensei" if account.role == "sensei" else "/student"
    return RedirectResponse(url=destination, status_code=303)


@app.get(
    "/",
    response_class=HTMLResponse,
)
async def dashboard(
    request: Request,
    current_user: AppUser | None = Depends(get_optional_current_account),
) -> Response:
    if current_user is not None:
        destination = "/sensei" if current_user.role == "sensei" else "/student"
        return RedirectResponse(url=destination, status_code=303)
    async with SessionLocal() as session:
        kanji_counts = dict(
            (await session.execute(select(Kanji.level, func.count()).group_by(Kanji.level))).all()
        )
        vocabulary_count = await session.scalar(select(func.count()).select_from(Vocabulary)) or 0
        grammar_count = await session.scalar(select(func.count()).select_from(Bunpou)) or 0
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "kanji_counts": kanji_counts,
            "vocabulary_count": vocabulary_count,
            "grammar_count": grammar_count,
        },
    )
