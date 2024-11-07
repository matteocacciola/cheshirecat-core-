from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource
from cat.convo.messages import ConversationHistory

router = APIRouter()


class DeleteConversationHistoryResponse(BaseModel):
    deleted: bool


class GetConversationHistoryResponse(BaseModel):
    history: ConversationHistory


# DELETE conversation history from working memory
@router.delete("/conversation_history", response_model=DeleteConversationHistoryResponse)
async def destroy_conversation_history(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.DELETE)),
) -> DeleteConversationHistoryResponse:
    """Delete the specified user's conversation history from working memory"""

    cats.stray_cat.working_memory.reset_history()

    return DeleteConversationHistoryResponse(deleted=True)


# GET conversation history from working memory
@router.get("/conversation_history", response_model=GetConversationHistoryResponse)
async def get_conversation_history(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.READ)),
) -> GetConversationHistoryResponse:
    """Get the specified user's conversation history from working memory"""

    return GetConversationHistoryResponse(history=cats.stray_cat.working_memory.history)
