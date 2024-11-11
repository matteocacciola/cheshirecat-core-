# Helper classes for connection handling
# Credential extraction from ws / http connections is not delegated to the custom auth handlers,
# to have a standard auth interface.
import asyncio
from abc import ABC, abstractmethod
from fastapi import Request, WebSocket, HTTPException, WebSocketException
from fastapi.requests import HTTPConnection
from pydantic import BaseModel, ConfigDict

from cat.bill_the_lizard import BillTheLizard
from cat.auth.auth_utils import extract_agent_id_from_request
from cat.auth.permissions import (
    AdminAuthResource,
    AuthPermission,
    AuthResource,
    AuthUserInfo,
    get_full_admin_permissions,
)
from cat.db.cruds import users as crud_users
from cat.factory.custom_auth_handler import BaseAuthHandler
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.looking_glass.stray_cat import StrayCat
from cat.log import log


class ContextualCats(BaseModel):
    cheshire_cat: CheshireCat
    stray_cat: StrayCat

    model_config = ConfigDict(arbitrary_types_allowed=True)


class AdminConnectionAuth:
    def __init__(self, resource: AdminAuthResource, permission: AuthPermission):
        self.resource = resource
        self.permission = permission

    async def __call__(self, request: Request) -> BillTheLizard:
        lizard: BillTheLizard = request.app.state.lizard

        user: AuthUserInfo = await lizard.core_auth_handler.authorize(
            request,
            self.resource,
            self.permission,
            key_id=lizard.config_key,
            http_permissions=get_full_admin_permissions(),
        )
        if user:
            return lizard

        self.not_allowed(request)

    def not_allowed(self, connection: Request, **kwargs):
        raise HTTPException(status_code=403, detail={"error": "Invalid Credentials"})


class ConnectionAuth(ABC):
    def __init__(self, resource: AuthResource, permission: AuthPermission):
        self.resource = resource
        self.permission = permission

    async def __call__(
        self,
        connection: HTTPConnection # Request | WebSocket,
    ) -> ContextualCats:
        agent_id = extract_agent_id_from_request(connection)

        lizard: BillTheLizard = connection.app.state.lizard
        ccat = lizard.get_or_create_cheshire_cat(agent_id)

        auth_handlers = [
            lizard.core_auth_handler,  # try to get user from local id
            ccat.custom_auth_handler,  # try to get user from auth_handler
        ]

        # is that an admin able to manage agents?
        user = await lizard.core_auth_handler.authorize(
            connection,
            AdminAuthResource.CHESHIRE_CATS,
            self.permission,
            key_id=lizard.config_key,
            http_permissions=get_full_admin_permissions(),
        )

        # no admin was found? try to look for agent's users
        counter = 0
        while not user and counter < len(auth_handlers):
            user = await self.get_agent_user_info(connection, auth_handlers[counter], agent_id)
            counter += 1

        if not user:
            # if no user was obtained, raise exception
            self.not_allowed(connection)

        stray = await self.get_user_stray(ccat, user, connection)
        return ContextualCats(cheshire_cat=ccat, stray_cat=stray)

    @abstractmethod
    async def get_agent_user_info(
        self, connection: HTTPConnection, auth_handler: BaseAuthHandler, agent_id: str
    ) -> AuthUserInfo | None:
        pass

    @abstractmethod
    async def get_user_stray(self, ccat: CheshireCat, user: AuthUserInfo, connection: HTTPConnection) -> StrayCat:
        pass

    @abstractmethod
    def not_allowed(self, connection: HTTPConnection, **kwargs):
        pass
        

class HTTPAuth(ConnectionAuth):
    async def get_agent_user_info(
        self, connection: HTTPConnection, auth_handler: BaseAuthHandler, agent_id: str
    ) -> AuthUserInfo | None:
        user = await auth_handler.authorize(
            connection,
            self.resource,
            self.permission,
            key_id=agent_id,
        )
        return user

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
    async def get_agent_user_info(
        self, connection: HTTPConnection, auth_handler: BaseAuthHandler, agent_id: str
    ) -> AuthUserInfo | None:
        user_id = auth_handler.extract_user_id_websocket(connection)
        if user_id and not crud_users.get_user(agent_id, user_id):
            crud_users.create_user(agent_id, {"id": user_id, "username": user_id, "password": user_id})

        user = await auth_handler.authorize(
            connection,
            self.resource,
            self.permission,
            key_id=agent_id,
        )
        return user

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
