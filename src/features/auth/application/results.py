from dataclasses import dataclass

from ..domain.entities import AuthenticatedUser


@dataclass(frozen=True)
class LoginResult:
    access_token: str
    refresh_token: str
    expires_in: int
    user: AuthenticatedUser


@dataclass(frozen=True)
class RefreshResult:
    access_token: str
    refresh_token: str
    expires_in: int
