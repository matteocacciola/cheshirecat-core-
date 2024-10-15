from typing import Dict, List
from fastapi import APIRouter, Request, Query, HTTPException

from cat.auth.auth_utils import extract_agent_id_from_request
from cat.auth.permissions import get_full_permissions
from cat.routes.auth_utils import (
    UserCredentials,
    JWTResponse,
    auth_login as fnc_login,
    auth_token as fnc_auth_token,
    auth_redirect as fnc_redirect,
)

router = APIRouter()


# set cookies and redirect to origin page after login
@router.post("/redirect", include_in_schema=False)
async def redirect(request: Request):
    # get agent_id from request
    form_data = await request.form()
    agent_id = form_data.get("agent_id")

    if not agent_id:
        raise HTTPException(status_code=404, detail={"error": "Forbidden access"})

    return await fnc_redirect(request, agent_id, f"/auth/{agent_id}/login/")


@router.get("/{agent_id}/login", include_in_schema=False)
async def login(request: Request, agent_id: str, referer: str = Query(None), retry: int = Query(0)):
    """Core login form, used when no external Identity Provider is configured"""

    return fnc_login(request, "/auth/redirect", referer=referer, retry=retry, agent_id=agent_id)


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
