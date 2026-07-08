"""Helpers de cookie HttpOnly para el refresh token (mitigación XSS)."""

from starlette.responses import Response

from src.shared.config import get_settings


def set_refresh_token_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=token,
        path=settings.refresh_token_cookie_path,
        httponly=True,
        secure=settings.refresh_token_cookie_secure,
        samesite="strict",
        max_age=settings.jwt_refresh_token_expire_days * 86400,
    )


def clear_refresh_token_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.refresh_token_cookie_name,
        path=settings.refresh_token_cookie_path,
        samesite="strict",
        secure=settings.refresh_token_cookie_secure,
    )
