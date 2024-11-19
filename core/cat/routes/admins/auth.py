from fastapi import APIRouter

from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.routes.routes_utils import UserCredentials, JWTResponse, auth_token as fnc_auth_token

router = APIRouter()


@router.post("/token", response_model=JWTResponse)
async def system_auth_token(credentials: UserCredentials):
    """Endpoint called from client to get a JWT from local identity provider.
    This endpoint receives username and password as form-data, validates credentials and issues a JWT.
    """

    return await fnc_auth_token(credentials, DEFAULT_SYSTEM_KEY)
