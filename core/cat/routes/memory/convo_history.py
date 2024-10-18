from typing import Dict
from fastapi import APIRouter, Depends

from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource

router = APIRouter()


# DELETE conversation history from working memory
@router.delete("/conversation_history")
async def wipe_conversation_history(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.DELETE)),
) -> Dict:
    """Delete the specified user's conversation history from working memory"""

    cats.stray_cat.working_memory.reset_conversation_history()

    return {"deleted": True}


# GET conversation history from working memory
@router.get("/conversation_history")
async def get_conversation_history(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.READ)),
) -> Dict:
    """Get the specified user's conversation history from working memory"""

    return {"history": cats.stray_cat.working_memory.history}
