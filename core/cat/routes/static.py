from fastapi import Request, FastAPI
from fastapi.staticfiles import StaticFiles

from cat.auth.connection import HTTPAuth
from cat.auth.permissions import AuthPermission, AuthResource
from cat.exceptions import CustomForbiddenException


class AuthStatic(StaticFiles):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    async def __call__(self, scope, receive, send) -> None:
        request = Request(scope, receive=receive)
        stray_http_auth = HTTPAuth(
            resource=AuthResource.STATIC, permission=AuthPermission.READ
        )
        allowed = await stray_http_auth(request)
        if not allowed:
            raise CustomForbiddenException("Forbidden.")
        await super().__call__(scope, receive, send)

def mount(cheshire_cat_api: FastAPI):
    # static files folder available to plugins
    # TODOAUTH: test static files auth
    cheshire_cat_api.mount(
        "/static/", AuthStatic(directory="cat/static"), name="static"
    )
