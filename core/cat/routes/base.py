from fastapi import APIRouter, Depends, Body
from fastapi.concurrency import run_in_threadpool
from typing import Dict
import tomli
from pydantic import BaseModel

from cat.auth.permissions import AuthPermission, AuthResource
from cat.auth.connection import HTTPAuth, ContextualCats
from cat.convo.messages import CatMessage, UserMessage

router = APIRouter()


class HomeResponse(BaseModel):
    status: str
    version: str


# server status
@router.get(
    "/",
    dependencies=[Depends(HTTPAuth(AuthResource.STATUS, AuthPermission.READ))],
    response_model=HomeResponse,
    tags=["Home"]
)
async def home() -> HomeResponse:
    """Server status"""
    with open("pyproject.toml", "rb") as f:
        project_toml = tomli.load(f)["project"]

    return HomeResponse(status="We're all mad here, dear!", version=project_toml["version"])


@router.post("/message", response_model=CatMessage, tags=["Message"])
async def message_with_cat(
    payload: Dict = Body(...),
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.CONVERSATION, AuthPermission.WRITE)),
) -> CatMessage:
    """Get a response from the Cat"""
    stray = cats.stray_cat

    user_message = UserMessage(
        user_id=stray.user.id, agent_id=stray.agent_id, text=payload["text"], image=payload.get("image")
    )
    answer = await run_in_threadpool(stray.run, user_message, True)
    return answer
