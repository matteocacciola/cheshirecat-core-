from typing import Dict, List
from fastapi import APIRouter, Request

from cat.auth.auth_utils import extract_agent_id_from_request
from cat.auth.permissions import get_full_permissions
from cat.routes.routes_utils import UserCredentials, JWTResponse, auth_token as fnc_auth_token

router = APIRouter()


@router.get("/available-permissions", response_model=Dict[str, List[str]])
async def get_available_permissions() -> Dict[str, List[str]]:
    """Returns all available resources and permissions."""
    return get_full_permissions()


@router.post("/token", response_model=JWTResponse)
async def auth_token(request: Request, credentials: UserCredentials) -> JWTResponse:
    """Endpoint called from client to get a JWT from local identity provider.
    This endpoint receives username and password as form-data, validates credentials and issues a JWT.
    """

    agent_id = extract_agent_id_from_request(request)

    return await fnc_auth_token(request, credentials, agent_id)
