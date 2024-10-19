from fastapi import APIRouter, Request

from cat.routes.routes_utils import UserCredentials, JWTResponse, auth_token as fnc_auth_token
from cat.utils import DEFAULT_SYSTEM_KEY

router = APIRouter()


@router.post("/token", response_model=JWTResponse)
async def auth_token(request: Request, credentials: UserCredentials):
    """Endpoint called from client to get a JWT from local identity provider.
    This endpoint receives username and password as form-data, validates credentials and issues a JWT.
    """

    return await fnc_auth_token(request, credentials, DEFAULT_SYSTEM_KEY)
