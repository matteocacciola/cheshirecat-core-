from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Literal, Dict, List
from pytz import utc
import jwt

from cat.auth.permissions import (
    AdminAuthResource,
    AuthPermission,
    AuthResource,
    AuthUserInfo,
    get_base_permissions,
    get_full_permissions,
)
from cat.auth.auth_utils import is_jwt
from cat.db.cruds import users as crud_users
from cat.env import get_env
from cat.log import log


class BaseAuthHandler(ABC):
    """
    Base class to build custom Auth systems that will live alongside core auth.
    Methods `authorize_user_from_credential`
    MUST be implemented by subclasses.
    """

    # when there is no JWT, user id is passed via `user_id: xxx` header or via websocket path
    # with JWT, the user id is in the token ad has priority
    async def authorize_user_from_credential(
        self,
        protocol: Literal["http", "websocket"],
        credential: str,
        auth_resource: AuthResource | AdminAuthResource,
        auth_permission: AuthPermission,
        user_id: str = "user",
        **kwargs,
    ) -> AuthUserInfo | None:
        if is_jwt(credential):
            # JSON Web Token auth
            return await self.authorize_user_from_jwt(credential, auth_resource, auth_permission, **kwargs)
        # API_KEY auth
        return await self.authorize_user_from_key(
            protocol, user_id, credential, auth_resource, auth_permission, **kwargs
        )

    @abstractmethod
    async def authorize_user_from_jwt(
        self,
        token: str,
        auth_resource: AuthResource | AdminAuthResource,
        auth_permission: AuthPermission,
        **kwargs,
    ) -> AuthUserInfo | None:
        # will raise: NotImplementedError
        pass

    @abstractmethod
    async def authorize_user_from_key(
        self,
        protocol: Literal["http", "websocket"],
        user_id: str,
        api_key: str,
        auth_resource: AuthResource | AdminAuthResource,
        auth_permission: AuthPermission,
        **kwargs,
    ) -> AuthUserInfo | None:
        # will raise: NotImplementedError
        pass


# Core auth handler, verify token on local idp
class CoreAuthHandler(BaseAuthHandler):
    async def authorize_user_from_jwt(
        self,
        token: str,
        auth_resource: AuthResource | AdminAuthResource,
        auth_permission: AuthPermission,
        **kwargs,
    ) -> AuthUserInfo | None:
        key_id = kwargs.get("key_id")

        try:
            # decode token
            payload = jwt.decode(token, get_env("CCAT_JWT_SECRET"), algorithms=[get_env("CCAT_JWT_ALGORITHM")])
        except Exception as e:
            log.error(f"Could not auth user from JWT: {e}")
            # do not pass
            return None

        # get user from DB
        users = crud_users.get_users(key_id)
        if payload["sub"] not in users.keys():
            # do not pass
            return None

        user = users[payload["sub"]]
        ar = str(auth_resource)
        ap = str(auth_permission)

        if ar not in user["permissions"].keys() or ap not in user["permissions"][ar]:
            # do not pass
            return None

        return AuthUserInfo(
            id=payload["sub"],
            name=payload["username"],
            permissions=user["permissions"],
            extra=user,
        )

    async def authorize_user_from_key(
        self,
        protocol: Literal["http", "websocket"],
        user_id: str,
        api_key: str,
        auth_resource: AuthResource | AdminAuthResource,
        auth_permission: AuthPermission,
        **kwargs,
    ) -> AuthUserInfo | None:
        """
        Authorize a user from an API key. This method is used to authorize users when they are not using a JWT token.
        Args:
            protocol: the protocol used to authorize the user (either "http" or "websocket")
            user_id: the user ID to authorize
            api_key: the API key to authorize the user
            auth_resource: the resource to authorize the user on
            auth_permission: the permission to authorize the user on

        Returns:
            An AuthUserInfo object if the user is authorized, None otherwise.
        """

        http_key = get_env("CCAT_API_KEY")
        ws_key = get_env("CCAT_API_KEY_WS")

        if not http_key and not ws_key:
            return None

        if protocol == "websocket":
            permissions = kwargs.get("websocket_permissions", get_base_permissions())
            return self._authorize_websocket_key(user_id, api_key, ws_key, permissions)

        permissions = kwargs.get("http_permissions", get_full_permissions())
        return self._authorize_http_key(user_id, api_key, http_key, permissions)

    def _authorize_http_key(
        self, user_id: str, api_key: str, http_key: str, permissions: Dict[str, List[str]]
    ) -> AuthUserInfo | None:
        # HTTP API key match -> allow access with full permissions
        if api_key == http_key:
            return AuthUserInfo(
                id=user_id,
                name=user_id,
                permissions=permissions
            )

        # No match -> deny access
        return None

    def _authorize_websocket_key(
            self, user_id: str, api_key: str, ws_key: str, permissions: Dict[str, List[str]]
    ) -> AuthUserInfo | None:
        # WebSocket API key match -> allow access with base permissions
        if api_key == ws_key:
            return AuthUserInfo(
                id=user_id,
                name=user_id,
                permissions=permissions
            )

        # No match -> deny access
        return None

    async def issue_jwt(self, username: str, password: str, **kwargs) -> str | None:
        """
        Authenticate local user credentials and return a JWT token.

        Args:
            username: the username of the user to authenticate
            password: the password of the user to authenticate

        Returns:
            A JWT token if the user is authenticated, None otherwise.
        """

        key_id = kwargs.get("key_id")

        # brutal search over users, which are stored in a simple dictionary.
        # waiting to have graph in core to store them properly
        user = crud_users.get_user_by_credentials(key_id, username, password)
        if not user:
            return None

        # TODOAUTH: expiration with timezone needs to be tested
        # using seconds for easier testing
        expire_delta_in_seconds = float(get_env("CCAT_JWT_EXPIRE_MINUTES")) * 60
        expires = datetime.now(utc) + timedelta(seconds=expire_delta_in_seconds)

        # TODOAUTH: add issuer and redirect_uri (and verify them when a token is validated)
        jwt_content = {
            "sub": user["id"],                   # Subject (the user ID)
            "username": username,                # Username
            "permissions": user["permissions"],  # User permissions
            "exp": expires                       # Expiry date as a Unix timestamp
        }
        return jwt.encode(jwt_content, get_env("CCAT_JWT_SECRET"), algorithm=get_env("CCAT_JWT_ALGORITHM"))


# Default Auth, always deny auth by default (only core auth decides).
class CoreOnlyAuthHandler(BaseAuthHandler):
    async def authorize_user_from_jwt(*args, **kwargs) -> AuthUserInfo | None:
        return None

    async def authorize_user_from_key(*args, **kwargs) -> AuthUserInfo | None:
        return None