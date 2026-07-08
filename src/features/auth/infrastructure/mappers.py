from ..domain.entities import AuthenticatedUser
from .schemas import AuthResponseDTO, TokenResponseDTO, UserDTO


def user_to_dto(user: AuthenticatedUser) -> UserDTO:
    return UserDTO(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        role=user.role_code,
        entity_id=user.entity_id,
        department_id=user.department_id,
        is_external=user.is_external,
    )


def login_result_to_dto(access_token: str, expires_in: int, user: AuthenticatedUser) -> AuthResponseDTO:
    return AuthResponseDTO(access_token=access_token, expires_in=expires_in, user=user_to_dto(user))


def token_result_to_dto(access_token: str, expires_in: int) -> TokenResponseDTO:
    return TokenResponseDTO(access_token=access_token, expires_in=expires_in)
