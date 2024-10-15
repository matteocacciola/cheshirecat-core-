from fastapi import APIRouter, Depends, Body
from fastapi.concurrency import run_in_threadpool
from typing import Dict
import tomli

from cat.auth.permissions import AuthPermission, AuthResource
from cat.auth.connection import HTTPAuth, ContextualCats
from cat.convo.messages import CatMessage

router = APIRouter()


# server status
@router.get("/", dependencies=[Depends(HTTPAuth(AuthResource.STATUS, AuthPermission.READ))])
async def home() -> Dict:
    """Server status"""
    with open("pyproject.toml", "rb") as f:
        project_toml = tomli.load(f)["project"]

    return {"status": "We're all mad here, dear!", "version": project_toml["version"]}


@router.post("/message", response_model=CatMessage)
async def message_with_cat(
    payload: Dict = Body(...),
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.CONVERSATION, AuthPermission.WRITE)),
) -> Dict:
    """Get a response from the Cat"""
    stray = cats.stray_cat

    user_message_json = {"user_id": stray.user_id, **payload}
    answer = await run_in_threadpool(stray.run, user_message_json, True)
    return {**answer, **{"user_id": stray.user_id, "agent_id": cats.cheshire_cat.id}}
