import asyncio
from abc import ABC, abstractmethod
from fastapi import Request, WebSocket, HTTPException, WebSocketException
from fastapi.requests import HTTPConnection
from pydantic import BaseModel, ConfigDict

from cat.auth.auth_utils import extract_agent_id_from_request
from cat.auth.permissions import (
    AdminAuthResource,
    AuthPermission,
    AuthResource,
    AuthUserInfo,
    get_full_admin_permissions,
    get_base_permissions,
)
from cat.db.cruds import users as crud_users
from cat.factory.custom_auth_handler import BaseAuthHandler
from cat.looking_glass.bill_the_lizard import BillTheLizard
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.looking_glass.stray_cat import StrayCat


class ContextualCats(BaseModel):
    cheshire_cat: CheshireCat
    stray_cat: StrayCat

    model_config = ConfigDict(arbitrary_types_allowed=True)


class AdminConnectionAuth:
    def __init__(self, resource: AdminAuthResource, permission: AuthPermission):
        self.resource = resource
        self.permission = permission

    def __call__(self, request: Request) -> BillTheLizard:
        lizard: BillTheLizard = request.app.state.lizard

        user: AuthUserInfo = lizard.core_auth_handler.authorize(
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

    async def __call__(self, connection: HTTPConnection) -> ContextualCats:
        agent_id = extract_agent_id_from_request(connection)
        lizard: BillTheLizard = connection.app.state.lizard
        ccat = lizard.get_cheshire_cat(agent_id)

        user = self.get_user_from_auth_handlers(connection, lizard, ccat)

        if not user:
            # if no user was obtained, raise exception
            self.not_allowed(connection)

        stray = await self.get_user_stray(ccat, user, connection)
        return ContextualCats(cheshire_cat=ccat, stray_cat=stray)

    def get_user_from_auth_handlers(
        self, connection: HTTPConnection, lizard: BillTheLizard, ccat: CheshireCat
    ) -> AuthUserInfo | None:
        auth_handlers = [
            lizard.core_auth_handler,  # try to get user from local id
            ccat.custom_auth_handler,  # try to get user from auth_handler
        ]

        # is that an admin able to manage agents?
        user = lizard.core_auth_handler.authorize(
            connection,
            AdminAuthResource.CHESHIRE_CATS,
            self.permission,
            key_id=lizard.config_key,
            http_permissions=get_full_admin_permissions(),
        )

        # no admin was found? try to look for agent's users
        counter = 0
        while not user and counter < len(auth_handlers):
            user = self.get_agent_user_info(connection, auth_handlers[counter], ccat.id)
            counter += 1

        return user

    @abstractmethod
    def get_agent_user_info(
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
    def get_agent_user_info(
        self, connection: Request, auth_handler: BaseAuthHandler, agent_id: str
    ) -> AuthUserInfo | None:
        user = auth_handler.authorize(
            connection,
            self.resource,
            self.permission,
            key_id=agent_id,
        )
        return user

    async def get_user_stray(self, ccat: CheshireCat, user: AuthUserInfo, connection: Request) -> StrayCat:
        return StrayCat(user_data=user, main_loop=connection.app.state.event_loop, agent_id=ccat.id)
    
    def not_allowed(self, connection: Request, **kwargs):
        raise HTTPException(status_code=403, detail={"error": "Invalid Credentials"})


class HTTPAuthMessage(HTTPAuth):
    def get_user_from_auth_handlers(
        self, connection: Request, lizard: BillTheLizard, ccat: CheshireCat
    ) -> AuthUserInfo | None:
        auth_handlers = [
            lizard.core_auth_handler,  # try to get user from local id
            ccat.custom_auth_handler,  # try to get user from auth_handler
        ]

        user = None
        counter = 0
        while not user and counter < len(auth_handlers):
            user = self.get_agent_user_info(connection, auth_handlers[counter], ccat.id)
            counter += 1

        return user


class WebSocketAuth(ConnectionAuth):
    def get_user_from_auth_handlers(
        self, connection: WebSocket, lizard: BillTheLizard, ccat: CheshireCat
    ) -> AuthUserInfo | None:
        auth_handlers = [
            lizard.core_auth_handler,  # try to get user from local id
            ccat.custom_auth_handler,  # try to get user from auth_handler
        ]

        user = None
        counter = 0
        while not user and counter < len(auth_handlers):
            user = self.get_agent_user_info(connection, auth_handlers[counter], ccat.id)
            counter += 1

        return user

    def get_agent_user_info(
        self, connection: WebSocket, auth_handler: BaseAuthHandler, agent_id: str
    ) -> AuthUserInfo | None:
        user_id = auth_handler.extract_user_id_websocket(connection)
        if user_id:
            crud_users.create_user(
                agent_id,
                {"id": user_id, "username": user_id, "password": user_id, "permissions": get_base_permissions()},
            )

        user = auth_handler.authorize(
            connection,
            self.resource,
            self.permission,
            key_id=agent_id,
        )
        return user

    async def get_user_stray(self, ccat: CheshireCat, user: AuthUserInfo, connection: WebSocket) -> StrayCat:
        return StrayCat(user_data=user, main_loop=asyncio.get_running_loop(), agent_id=ccat.id, ws=connection)

    def not_allowed(self, connection: WebSocket, **kwargs):
        raise WebSocketException(code=1004, reason="Invalid Credentials")
