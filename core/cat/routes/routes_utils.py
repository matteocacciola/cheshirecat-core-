import asyncio
from typing import Dict, List, Any
from pydantic import BaseModel
from fastapi import Request, HTTPException

from cat.utils import ReplacedNLPConfig


class UserCredentials(BaseModel):
    username: str
    password: str


class JWTResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UpsertSettingResponse(ReplacedNLPConfig):
    pass


class GetSettingResponse(UpsertSettingResponse):
    scheme: Dict[str, Any] | None = None


class GetSettingsResponse(BaseModel):
    settings: List[GetSettingResponse]
    selected_configuration: str | None


async def auth_token(request: Request, credentials: UserCredentials, agent_id: str):
    """Endpoint called from client to get a JWT from local identity provider.
    This endpoint receives username and password as form-data, validates credentials and issues a JWT.
    """

    # use username and password to authenticate user from local identity provider and get token
    access_token = await request.app.state.lizard.core_auth_handler.issue_jwt(
        credentials.username, credentials.password, key_id=agent_id
    )

    if access_token:
        return JWTResponse(access_token=access_token)

    # Invalid username or password
    # wait a little to avoid brute force attacks
    await asyncio.sleep(1)
    raise HTTPException(status_code=403, detail={"error": "Invalid Credentials"})
