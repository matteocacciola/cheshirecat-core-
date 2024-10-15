from typing import Dict, List
from fastapi import APIRouter, Request, Query, HTTPException

from cat.auth.auth_utils import extract_agent_id_from_request
from cat.auth.permissions import get_full_permissions
from cat.routes.auth_utils import (
    UserCredentials,
    JWTResponse,
    auth_index as fnc_auth_index,
    auth_token as fnc_auth_token,
    core_login_token as fnc_core_login_token,
)

router = APIRouter()


# set cookies and redirect to origin page after login
@router.post("/redirect", include_in_schema=False)
async def core_login_token(request: Request):
    # get agent_id from request
    agent_id = extract_agent_id_from_request(request)
    if not agent_id:
        raise HTTPException(status_code=404, detail={"error": "Forbidden access"})

    return await fnc_core_login_token(request, agent_id, "/auth/login")


@router.get("/login", include_in_schema=False)
async def auth_index(request: Request, referer: str = Query(None), retry: int = Query(0)):
    """Core login form, used when no external Identity Provider is configured"""

    return fnc_auth_index(request, "/auth/redirect", referer, retry)


# TODOAUTH /logout endpoint

@router.get("/available-permissions", response_model=Dict[str, List[str]])
async def get_available_permissions():
    """Returns all available resources and permissions."""
    return get_full_permissions()


@router.post("/token", response_model=JWTResponse)
async def auth_token(request: Request, credentials: UserCredentials):
    """Endpoint called from client to get a JWT from local identity provider.
    This endpoint receives username and password as form-data, validates credentials and issues a JWT.
    """

    agent_id = extract_agent_id_from_request(request)
    if not agent_id:
        raise HTTPException(status_code=404, detail={"error": "Forbidden access"})

    return await fnc_auth_token(request, credentials, agent_id)
