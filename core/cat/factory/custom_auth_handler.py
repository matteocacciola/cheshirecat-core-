from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Literal, Dict, List
from pytz import utc
import jwt
from fastapi import Request

from cat.auth.auth_utils import is_jwt, extract_token, extract_user_info
from cat.auth.permissions import (
    AdminAuthResource,
    AuthPermission,
    AuthResource,
    AuthUserInfo,
    get_base_permissions,
    get_full_permissions,
)
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
    async def authorize(
        self,
        request: Request,
        auth_resource: AuthResource | AdminAuthResource,
        auth_permission: AuthPermission,
        **kwargs,
    ) -> AuthUserInfo | None:
        """
        Authorize a user based on the request and the given resource and permission. This method will extract the token
        from the request and call the appropriate authorization method based on the protocol used. If the token is a JWT,
        it will call `authorize_user_from_jwt`, otherwise it will call `authorize_user_from_key`. If the user is
        authorized, it will return an AuthUserInfo object, otherwise it will return None.

        Args:
            request: the Starlette request to authorize the user on
            auth_resource: the resource to authorize the user on
            auth_permission: the permission to authorize the user on
            **kwargs: additional keyword arguments

        Returns:
            An AuthUserInfo object if the user is authorized, None otherwise.
        """

        # get protocol from Starlette request
        protocol = request.scope.get("type")

        # extract token from request
        if protocol == "http":
            token = self.extract_token_http(request)
        elif protocol == "websocket":
            token = self.extract_token_websocket(request)
        else:
            log.error(f"Unknown protocol: {protocol}")
            return None

        if not token:
            return None

        if is_jwt(token):
            # JSON Web Token auth
            return await self.authorize_user_from_jwt(token, auth_resource, auth_permission, **kwargs)

        user_id = request.headers.get("user_id")
        # API_KEY auth
        return await self.authorize_user_from_key(protocol, token, auth_resource, auth_permission, user_id, **kwargs)

    @abstractmethod
    def extract_token_http(self, request: Request) -> str | None:
        """
        Extract the token from an HTTP request. This method is used to extract the token from the request when the user
        is using an HTTP protocol. It should return the token if it is found, otherwise it should return None.

        Args:
            request: the Starlette request to extract the token from (HTTP)

        Returns:
            The token if it is found, None otherwise.
        """

        # will raise: NotImplementedError
        pass

    @abstractmethod
    def extract_token_websocket(self, request: Request) -> str | None:
        """
        Extract the token from a WebSocket request. This method is used to extract the token from the request when the
        user is using a WebSocket protocol. It should return the token if it is found, otherwise it should return None.

        Args:
            request: the Starlette request to extract the token from (WebSocket)

        Returns:
            The token if it is found, None otherwise.
        """

        # will raise: NotImplementedError
        pass

    @abstractmethod
    async def authorize_user_from_jwt(
        self,
        token: str,
        auth_resource: AuthResource | AdminAuthResource,
        auth_permission: AuthPermission,
        **kwargs,
    ) -> AuthUserInfo | None:
        """
        Authorize a user from a JWT token. This method is used to authorize users when they are using a JWT token.

        Args:
            token: the JWT token to authorize the user from
            auth_resource: the resource to authorize the user on
            auth_permission: the permission to authorize the user on
            **kwargs: additional keyword arguments

        Returns:
            An AuthUserInfo object if the user is authorized, None otherwise.
        """

        # will raise: NotImplementedError
        pass

    @abstractmethod
    async def authorize_user_from_key(
        self,
        protocol: Literal["http", "websocket"],
        api_key: str,
        auth_resource: AuthResource | AdminAuthResource,
        auth_permission: AuthPermission,
        request_user_id: str | None = None,
        **kwargs,
    ) -> AuthUserInfo | None:
        """
        Authorize a user from an API key. This method is used to authorize users when they are not using a JWT token.
        Args:
            protocol: the protocol used to authorize the user (either "http" or "websocket")
            api_key: the API key to authorize the user
            auth_resource: the resource to authorize the user on
            auth_permission: the permission to authorize the user on
            request_user_id: the user ID to authorize (it can be null)
            kwargs: additional keyword arguments

        Returns:
            An AuthUserInfo object if the user is authorized, None otherwise.
        """

        # will raise: NotImplementedError
        pass


# Core auth handler, verify token on local idp
class CoreAuthHandler(BaseAuthHandler):
    def extract_token_http(self, request: Request) -> str | None:
        # Proper Authorization header
        token = extract_token(request)
        return token

    def extract_token_websocket(self, request: Request) -> str | None:
        # Token passed as query parameter
        token = request.query_params.get("token", request.query_params.get("apikey"))
        return token

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
        user = crud_users.get_user(key_id, payload["sub"])
        if not user:
            # do not pass
            return None

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
        api_key: str,
        auth_resource: AuthResource | AdminAuthResource,
        auth_permission: AuthPermission,
        request_user_id: str | None = None,
        **kwargs,
    ) -> AuthUserInfo | None:
        http_key = get_env("CCAT_API_KEY")
        ws_key = get_env("CCAT_API_KEY_WS")

        if not http_key and not ws_key:
            return None

        key_id = kwargs.get("key_id")
        user_info = extract_user_info(key_id, request_user_id)
        if not user_info:
            return None

        if protocol == "websocket" and api_key == ws_key:
            permissions: Dict[str, List[str]] = kwargs.get("websocket_permissions", get_base_permissions())
            return AuthUserInfo(
                id=user_info.user_id,
                name=user_info.username,
                permissions=permissions
            )

        if protocol == "http" and api_key == http_key:
            permissions: Dict[str, List[str]] = kwargs.get("http_permissions", get_full_permissions())
            return AuthUserInfo(
                id=user_info.user_id,
                name=user_info.username,
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
            kwargs: additional keyword arguments

        Returns:
            A JWT token if the user is authenticated, None otherwise.
        """

        key_id = kwargs.get("key_id")

        # brutal search over users, which are stored in a simple dictionary.
        # waiting to have graph in core to store them properly
        user = crud_users.get_user_by_credentials(key_id, username, password)
        if not user:
            return None

        # TODO AUTH: expiration with timezone needs to be tested
        # using seconds for easier testing
        expire_delta_in_seconds = float(get_env("CCAT_JWT_EXPIRE_MINUTES")) * 60
        expires = datetime.now(utc) + timedelta(seconds=expire_delta_in_seconds)

        # TODO AUTH: add issuer and redirect_uri (and verify them when a token is validated)
        jwt_content = {
            "sub": user["id"],                   # Subject (the user ID)
            "username": username,                # Username
            "permissions": user["permissions"],  # User permissions
            "exp": expires                       # Expiry date as a Unix timestamp
        }
        return jwt.encode(jwt_content, get_env("CCAT_JWT_SECRET"), algorithm=get_env("CCAT_JWT_ALGORITHM"))


# Default Auth, always deny auth by default (only core auth decides).
class CoreOnlyAuthHandler(BaseAuthHandler):
    def extract_token_http(self, request: Request) -> str | None:
        return None

    def extract_token_websocket(self, request: Request) -> str | None:
        return None

    async def authorize_user_from_jwt(*args, **kwargs) -> AuthUserInfo | None:
        return None

    async def authorize_user_from_key(*args, **kwargs) -> AuthUserInfo | None:
        return None
