from fastapi import APIRouter, Depends, Body
from fastapi.concurrency import run_in_threadpool
from typing import Dict
from pydantic import BaseModel

from cat.auth.permissions import AuthPermission, AuthResource
from cat.auth.connection import HTTPAuth, ContextualCats
from cat.convo.messages import CatMessage, UserMessage
from cat.utils import get_cat_version

router = APIRouter()


class HomeResponse(BaseModel):
    status: str
    version: str


# server status
@router.get("/", response_model=HomeResponse, tags=["Home"])
async def home() -> HomeResponse:
    """Server status"""
    return HomeResponse(status="We're all mad here, dear!", version=get_cat_version())


@router.post("/message", response_model=CatMessage, tags=["Message"])
async def message_with_cat(
    payload: Dict = Body(...),
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.CONVERSATION, AuthPermission.WRITE)),
) -> CatMessage:
    """Get a response from the Cat"""
    stray = cats.stray_cat

    user_message = UserMessage(**payload)
    answer = await run_in_threadpool(stray.run_http, user_message)
    return answer
