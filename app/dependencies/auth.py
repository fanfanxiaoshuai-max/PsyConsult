import re
import secrets
from typing import Annotated
from fastapi import Header, HTTPException, status, Depends
from app.app_config.settings import settings

USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")

def authenticated_principal(authorization: str | None) -> tuple[str, str] | None:
    """Configured professional identities and personal sessions are independently verified."""
    token = _extract_bearer_token(authorization)
    configured = bool(settings.api_auth_users or settings.api_auth_token)
    if settings.api_auth_users:
        matches = [(uid, account.role) for uid, account in settings.api_auth_users.items()
                   if token and secrets.compare_digest(token, account.token.get_secret_value())]
        if len(matches) == 1 and USER_ID_PATTERN.fullmatch(matches[0][0]): return matches[0]
    elif settings.api_auth_token and token and secrets.compare_digest(token, settings.api_auth_token):
        return settings.api_local_user_id, settings.api_local_role
    if token and token.startswith('ps_'):
        from app.portal.store import session_principal
        principal = session_principal(token)
        if principal is not None: return principal
        raise HTTPException(401, 'Session expired or invalid')
    if not configured: return None
    raise HTTPException(401, 'Invalid or missing bearer token', headers={'WWW-Authenticate': 'Bearer'})


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def require_chat_identity(
    authorization: Annotated[str | None, Header()] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> str:
    principal = authenticated_principal(authorization)

    if principal and principal[1] == 'public':
        raise HTTPException(403, 'Professional workspace required')

    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-User-Id header",
        )

    user_id = x_user_id
    if not USER_ID_PATTERN.fullmatch(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-User-Id header",
        )
    if principal and user_id != principal[0]:
        raise HTTPException(403, 'X-User-Id does not match authenticated identity')
    return principal[0] if principal else user_id


def _require_role(actor, authorization, allowed):
    principal=authenticated_principal(authorization)
    if principal is None:raise HTTPException(401, 'Authentication required for knowledge changes')
    if principal[0]!=actor or principal[1] not in allowed:raise HTTPException(403, 'Insufficient knowledge management permissions')
    return actor


def require_reviewer_identity(actor: Annotated[str, Depends(require_chat_identity)],
                              authorization: Annotated[str | None, Header()] = None) -> str:
    return _require_role(actor, authorization, {'reviewer', 'admin'})


def require_admin_identity(actor: Annotated[str, Depends(require_chat_identity)],
                           authorization: Annotated[str | None, Header()] = None) -> str:
    return _require_role(actor, authorization, {'admin'})

