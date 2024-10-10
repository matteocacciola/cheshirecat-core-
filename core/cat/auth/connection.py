# Helper classes for connection handling
# Credential extraction from ws / http connections is not delegated to the custom auth handlers,
# to have a standard auth interface.
import asyncio
from abc import ABC, abstractmethod
from urllib.parse import urlencode
from fastapi import Request, WebSocket, HTTPException, WebSocketException
from fastapi.requests import HTTPConnection
from pydantic import BaseModel, ConfigDict

from cat.auth.permissions import AuthPermission, AuthResource, AuthUserInfo
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.looking_glass.cheshire_cat_manager import CheshireCatManager
from cat.looking_glass.stray_cat import StrayCat
from cat.log import log


class Credentials(BaseModel):
    chatbot_id: str
    user_id: str
    credential: str | None


class ContextualCats(BaseModel):
    cheshire_cat: CheshireCat
    stray_cat: StrayCat

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ConnectionAuth(ABC):
    def __init__(self, resource: AuthResource, permission: AuthPermission):
        self.resource = resource
        self.permission = permission

    async def __call__(
        self,
        connection: HTTPConnection # Request | WebSocket,
    ) -> ContextualCats:
        # extract credentials (user_id, token_or_key) from connection
        credentials = await self.extract_credentials(connection)

        ccat_manager: CheshireCatManager = connection.app.state.ccat_manager
        ccat = ccat_manager.get_or_create_cheshire_cat(credentials.chatbot_id)

        auth_handlers = [
            # try to get user from local id
            ccat_manager.core_auth_handler,
            # try to get user from auth_handler
            ccat.custom_auth_handler,
        ]
        for ah in auth_handlers:
            user: AuthUserInfo = await ah.authorize_user_from_credential(
                credentials.credential,
                self.resource,
                self.permission,
                user_id=credentials.user_id,
                chatbot_id=credentials.chatbot_id,
            )
            if user:
                stray = await self.get_user_stray(ccat, user, connection)
                return ContextualCats(cheshire_cat=ccat, stray_cat=stray)

        # if no stray was obtained, raise exception
        self.not_allowed(connection)

    @abstractmethod
    async def extract_credentials(self, connection: HTTPConnection) -> Credentials:
        pass

    @abstractmethod
    async def get_user_stray(self, ccat: CheshireCat, user: AuthUserInfo, connection: HTTPConnection) -> StrayCat:
        pass

    @abstractmethod
    def not_allowed(self, connection: HTTPConnection):
        pass
        

class HTTPAuth(ConnectionAuth):
    async def extract_credentials(self, connection: Request) -> Credentials:
        """
        Extract user_id and token/key from headers
        """

        # when using CCAT_API_KEY, chatbot_id and user_id are passed in headers
        chatbot_id = connection.headers.get("chatbot_id", "chatbot")
        user_id = connection.headers.get("user_id", "user")

        # Proper Authorization header
        token = connection.headers.get("Authorization", None)
        if token and ("Bearer " in token):
            token = token.replace("Bearer ", "")

        if not token:
            # Legacy header to pass CCAT_API_KEY
            token = connection.headers.get("access_token", None)
            if token:
                log.warning(
                    "Deprecation Warning: `access_token` header will not be supported in v2."
                    "Pass your token/key using the `Authorization: Bearer <token>` format."
                )
        
        # some clients may send an empty string instead of just not setting the header
        if token == "":
            token = None

        return Credentials(chatbot_id=chatbot_id, user_id=user_id, credential=token)

    async def get_user_stray(self, ccat: CheshireCat, user: AuthUserInfo, connection: Request) -> StrayCat:
        current_stray = ccat.get_stray(user.id)
        if current_stray:
            return current_stray

        event_loop = connection.app.state.event_loop
        stray_cat = StrayCat(user_data=user, main_loop=event_loop, chatbot_id=ccat.id)
        ccat.add_stray(stray_cat)

        return stray_cat
    
    def not_allowed(self, connection: Request):
        raise HTTPException(status_code=403, detail={"error": "Invalid Credentials"})
    

class WebSocketAuth(ConnectionAuth):
    async def extract_credentials(self, connection: WebSocket) -> Credentials:
        """
        Extract chatbot_id and user_id from WebSocket path params
        Extract token from WebSocket query string
        """
        chatbot_id = connection.path_params.get("chatbot_id", "chatbot")
        user_id = connection.path_params.get("user_id", "user")

        # TODO AUTH: is there a more secure way to pass the token over websocket?
        #   Headers do not work from the browser
        token = connection.query_params.get("token", None)
        
        return Credentials(chatbot_id=chatbot_id, user_id=user_id, credential=token)

    async def get_user_stray(self, ccat: CheshireCat, user: AuthUserInfo, connection: WebSocket) -> StrayCat:
        stray = ccat.get_stray(user.id)
        if stray:
            # Close previous ws connection
            if stray.ws:
                await stray.ws.close()
                log.info(
                    f"New websocket connection for user '{user.id}', the old one has been closed."
                )
            # Set new ws connection
            stray.ws = connection
            return stray

        # Create a new stray and add it to the current cheshire cat
        stray = StrayCat(user_data=user, main_loop=asyncio.get_running_loop(), chatbot_id=ccat.id, ws=connection)
        ccat.add_stray(stray)
        return stray

    def not_allowed(self, connection: WebSocket):
        raise WebSocketException(code=1004, reason="Invalid Credentials")


class CoreFrontendAuth(HTTPAuth):
    async def extract_credentials(self, connection: Request) -> Credentials:
        """
        Extract user_id from cookie
        """

        token = connection.cookies.get("ccat_user_token", None)

        # core webapps cannot be accessed without a cookie
        if token is None or token == "":
            self.not_allowed(connection)

        return Credentials(chatbot_id="chatbot", user_id="user", credential=token)
    
    def not_allowed(self, connection: Request):
        referer_query = urlencode({"referer": connection.url.path})
        raise HTTPException(
            status_code=307,
            headers={
                "Location": f"/auth/login?{referer_query}"
            }
        )