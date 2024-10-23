# Helper classes for connection handling
# Credential extraction from ws / http connections is not delegated to the custom auth handlers,
# to have a standard auth interface.
import asyncio
from abc import ABC, abstractmethod
from fastapi import Request, WebSocket, HTTPException, WebSocketException
from fastapi.requests import HTTPConnection
from pydantic import BaseModel, ConfigDict

from cat.bill_the_lizard import BillTheLizard
from cat.auth.auth_utils import extract_agent_id_from_request, extract_user_id_from_request, extract_token
from cat.auth.permissions import (
    AdminAuthResource,
    AuthPermission,
    AuthResource,
    AuthUserInfo,
    get_full_admin_permissions,
)
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.looking_glass.stray_cat import StrayCat
from cat.log import log


class SuperCredentials(BaseModel):
    user_id: str
    credential: str | None


class Credentials(SuperCredentials):
    agent_id: str


class ContextualCats(BaseModel):
    cheshire_cat: CheshireCat
    stray_cat: StrayCat

    model_config = ConfigDict(arbitrary_types_allowed=True)


class AdminConnectionAuth:
    def __init__(self, resource: AdminAuthResource, permission: AuthPermission):
        self.resource = resource
        self.permission = permission

    async def __call__(self, request: Request) -> BillTheLizard:
        # get protocol from Starlette request
        protocol = request.scope.get("type")

        # extract credentials (user_id, token_or_key) from connection
        user_id = extract_user_id_from_request(request)
        token = extract_token(request)

        lizard: BillTheLizard = request.app.state.lizard

        user: AuthUserInfo = await lizard.core_auth_handler.authorize_user_from_credential(
            protocol,
            token,
            self.resource,
            self.permission,
            key_id=lizard.config_key,
            user_id=user_id,
            http_permissions=get_full_admin_permissions(),
        )
        if user:
            return lizard

        raise HTTPException(status_code=403, detail={"error": "Invalid Credentials"})


class ConnectionAuth(ABC):
    def __init__(self, resource: AuthResource, permission: AuthPermission):
        self.resource = resource
        self.permission = permission

    async def __call__(
        self,
        connection: HTTPConnection # Request | WebSocket,
    ) -> ContextualCats:
        # get protocol from Starlette request
        protocol = connection.scope.get("type")

        # extract credentials (user_id, token_or_key) from connection
        credentials = await self.extract_credentials(connection)

        lizard: BillTheLizard = connection.app.state.lizard
        ccat = lizard.get_or_create_cheshire_cat(credentials.agent_id)

        auth_handlers = [
            lizard.core_auth_handler,  # try to get user from local id
            ccat.custom_auth_handler,  # try to get user from auth_handler
        ]

        # is that an admin able to manage agents?
        user: AuthUserInfo = await lizard.core_auth_handler.authorize_user_from_credential(
            protocol,
            credentials.credential,
            AdminAuthResource.CHESHIRE_CATS,
            self.permission,
            key_id=lizard.config_key,
            user_id=credentials.user_id,
            http_permissions=get_full_admin_permissions(),
        )

        # no admin was found? try to look for agent's users
        counter = 0
        while not user and counter < len(auth_handlers):
            user = await auth_handlers[counter].authorize_user_from_credential(
                protocol,
                credentials.credential,
                self.resource,
                self.permission,
                key_id=credentials.agent_id,
                user_id=credentials.user_id,
            )
            counter += 1

        if not user:
            # if no user was obtained, raise exception
            self.not_allowed(connection)

        stray = await self.get_user_stray(ccat, user, connection)
        return ContextualCats(cheshire_cat=ccat, stray_cat=stray)

    @abstractmethod
    async def extract_credentials(self, connection: HTTPConnection) -> Credentials:
        pass

    @abstractmethod
    async def get_user_stray(self, ccat: CheshireCat, user: AuthUserInfo, connection: HTTPConnection) -> StrayCat:
        pass

    @abstractmethod
    def not_allowed(self, connection: HTTPConnection, **kwargs):
        pass
        

class HTTPAuth(ConnectionAuth):
    async def extract_credentials(self, connection: Request) -> Credentials:
        """
        Extract user_id and token/key from headers
        """

        # when using CCAT_API_KEY, agent_id and user_id are passed in headers
        agent_id = extract_agent_id_from_request(connection)
        user_id = extract_user_id_from_request(connection)

        # Proper Authorization header
        token = extract_token(connection)

        return Credentials(agent_id=agent_id, user_id=user_id, credential=token)

    async def get_user_stray(self, ccat: CheshireCat, user: AuthUserInfo, connection: Request) -> StrayCat:
        current_stray = ccat.get_stray(user.id)
        if current_stray:
            return current_stray

        event_loop = connection.app.state.event_loop
        stray_cat = StrayCat(user_data=user, main_loop=event_loop, agent_id=ccat.id)
        ccat.add_stray(stray_cat)

        return stray_cat
    
    def not_allowed(self, connection: Request, **kwargs):
        raise HTTPException(status_code=403, detail={"error": "Invalid Credentials"})
    

class WebSocketAuth(ConnectionAuth):
    async def extract_credentials(self, connection: WebSocket) -> Credentials:
        """
        Extract agent_id and user_id from WebSocket path params
        Extract token from WebSocket query string
        """
        agent_id = extract_agent_id_from_request(connection)
        user_id = extract_user_id_from_request(connection)

        # TODO AUTH: is there a more secure way to pass the token over websocket?
        #   Headers do not work from the browser
        credential = connection.query_params.get("token", connection.query_params.get("apikey", None))

        return Credentials(agent_id=agent_id, user_id=user_id, credential=credential)

    async def get_user_stray(self, ccat: CheshireCat, user: AuthUserInfo, connection: WebSocket) -> StrayCat:
        stray: StrayCat = ccat.get_stray(user.id)
        if stray:
            await stray.close_connection()

            # Set new ws connection
            stray.reset_connection(connection)
            log.info(
                f"New websocket connection for user '{user.id}', the old one has been closed."
            )
            return stray

        # Create a new stray and add it to the current cheshire cat
        stray = StrayCat(user_data=user, main_loop=asyncio.get_running_loop(), agent_id=ccat.id, ws=connection)
        ccat.add_stray(stray)
        return stray

    def not_allowed(self, connection: WebSocket, **kwargs):
        raise WebSocketException(code=1004, reason="Invalid Credentials")
