from fastapi import APIRouter, Query, Request

from cat.routes.auth_utils import (
    UserCredentials,
    JWTResponse,
    auth_login as fnc_login,
    auth_token as fnc_auth_token,
    auth_redirect as fnc_redirect,
)
from cat.utils import DefaultAgentKeys

router = APIRouter()


# set cookies and redirect to origin page after login
@router.post("/redirect", include_in_schema=False)
async def redirect(request: Request):
    # get agent_id from request
    agent_id = str(DefaultAgentKeys.SYSTEM)

    return await fnc_redirect(request, agent_id, "/admins/auth/login")


@router.get("/login", include_in_schema=False)
async def login(request: Request, referer: str = Query(None), retry: int = Query(0)):
    """Core login form, used when no external Identity Provider is configured"""

    return fnc_login(request, "/admins/auth/redirect", referer=referer, retry=retry)


@router.post("/token", response_model=JWTResponse)
async def auth_token(request: Request, credentials: UserCredentials):
    """Endpoint called from client to get a JWT from local identity provider.
    This endpoint receives username and password as form-data, validates credentials and issues a JWT.
    """

    agent_id = str(DefaultAgentKeys.SYSTEM)

    return await fnc_auth_token(request, credentials, agent_id)