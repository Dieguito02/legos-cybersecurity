from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.core.config import settings
from backend.core.security import create_session_token, validate_credentials, verify_session_token

router = APIRouter(prefix="/api", tags=["auth"])


def _read_session_username(request: Request) -> str | None:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    return verify_session_token(token)


@router.post("/login")
async def login(request: Request):
    data = await request.json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not validate_credentials(username, password):
        return JSONResponse({"ok": False, "message": "Usuario o contraseña inválidos."}, status_code=401)

    token = create_session_token(username)
    response = JSONResponse({"ok": True, "message": "Autenticación correcta.", "user": {"username": username}})
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=settings.session_max_age_seconds,
    )
    return response


@router.post("/logout")
async def logout():
    response = JSONResponse({"ok": True, "message": "Sesión cerrada."})
    response.delete_cookie(settings.session_cookie_name)
    return response


@router.get("/user")
async def user(request: Request):
    username = _read_session_username(request)
    if not username:
        return JSONResponse({"ok": False, "authenticated": False}, status_code=401)
    return {"ok": True, "authenticated": True, "user": {"username": username}}
