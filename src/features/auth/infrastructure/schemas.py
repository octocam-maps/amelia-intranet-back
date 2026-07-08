"""DTOs de request/response (Pydantic). Único lugar del feature que FastAPI serializa."""

from typing import Optional

from pydantic import BaseModel


class LoginRequestDTO(BaseModel):
    id_token: str


class UserDTO(BaseModel):
    id: str
    email: str
    full_name: str
    avatar_url: Optional[str] = None
    role: str
    entity_id: Optional[str] = None
    department_id: Optional[str] = None
    is_external: bool


class AuthResponseDTO(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserDTO


class TokenResponseDTO(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
