from cat.auth.permissions import AuthPermission, AuthResource
from cat.auth.connection import WebSocketAuth, ContextualCats
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from fastapi.concurrency import run_in_threadpool

from cat.convo.messages import UserMessage
from cat.looking_glass.stray_cat import StrayCat
from cat.log import log

router = APIRouter()


async def receive_message(websocket: WebSocket, stray: StrayCat):
    """
    Continuously receive messages from the WebSocket and forward them to the `ccat` object for processing.
    """

    while True:
        # Receive the next message from the WebSocket.
        user_message_text = await websocket.receive_json()
        user_message = UserMessage(
            user_id=stray.user.id,
            agent_id=stray.agent_id,
            text=user_message_text["text"],
            image=user_message_text.get("image"),
            audio=user_message_text.get("audio"),
        )

        # Run the `stray` object's method in a threadpool since it might be a CPU-bound operation.
        await run_in_threadpool(stray.run, user_message, return_message=False)


@router.websocket("/ws")
@router.websocket("/ws/{agent_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    cats: ContextualCats = Depends(WebSocketAuth(AuthResource.CONVERSATION, AuthPermission.WRITE)),
):
    """
    Endpoint to handle incoming WebSocket connections by user id, process messages, and check for messages.
    """

    # Extract the StrayCat object from the DependingCats object.
    stray = cats.stray_cat

    # Add the new WebSocket connection to the manager.
    await websocket.accept()
    try:
        # Process messages
        await receive_message(websocket, stray)
    except WebSocketDisconnect:
        # Handle the event where the user disconnects their WebSocket.
        stray.nullify_connection()
        log.info("WebSocket connection closed")
