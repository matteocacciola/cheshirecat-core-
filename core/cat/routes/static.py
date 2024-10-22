from fastapi import Request, FastAPI
from fastapi.staticfiles import StaticFiles

from cat.auth.connection import HTTPAuth
from cat.auth.permissions import AuthPermission, AuthResource


class AuthStatic(StaticFiles):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    async def __call__(self, scope, receive, send) -> None:
        request = Request(scope, receive=receive)
        http_auth = HTTPAuth(resource=AuthResource.STATIC, permission=AuthPermission.READ)
        await http_auth(request)
        await super().__call__(scope, receive, send)

def mount(cheshire_cat_api: FastAPI):
    # static files folder available to plugins
    cheshire_cat_api.mount(
        "/static/", AuthStatic(directory="cat/static"), name="static"
    )
