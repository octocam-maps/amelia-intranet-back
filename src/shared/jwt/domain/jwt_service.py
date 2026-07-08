"""Puerto (Protocol) del servicio de JWT interno. Sin dependencias de framework."""

from datetime import datetime, timedelta
from typing import Any, Optional, Protocol


class IJWTService(Protocol):
    access_token_expire_minutes: int

    def create_access_token(
        self, data: dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str: ...

    def create_refresh_token(
        self, data: dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str: ...

    def verify_token(self, token: str) -> dict[str, Any]: ...

    def get_refresh_token_expires_at(self) -> datetime: ...
