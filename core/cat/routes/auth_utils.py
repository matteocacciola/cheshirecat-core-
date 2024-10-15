import asyncio
from urllib.parse import urlencode
from pydantic import BaseModel
from fastapi import Request, HTTPException, status, Query
from fastapi.responses import RedirectResponse

from cat.routes.static.templates import get_jinja_templates


class UserCredentials(BaseModel):
    username: str
    password: str


class JWTResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


async def core_login_token(request: Request, agent_id: str, route: str) -> RedirectResponse:
    # get form data from submitted core login form (/auth/core_login)
    form_data = await request.form()

    # use username and password to authenticate user from local identity provider and get token
    auth_handler = request.app.state.lizard.core_auth_handler
    access_token = await auth_handler.issue_jwt(form_data["username"], form_data["password"], key_id=agent_id)

    if access_token:
        response = RedirectResponse(
            url=form_data["referer"], status_code=status.HTTP_303_SEE_OTHER
        )
        response.set_cookie(key="ccat_user_token", value=access_token)
        return response

    # credentials are wrong, wait a second (for brute force attacks) and go back to login
    await asyncio.sleep(1)
    referer_query = urlencode(
        {
            "referer": form_data["referer"],
            "retry": 1,
        }
    )
    login_url = f"{route}?{referer_query}"
    response = RedirectResponse(url=login_url, status_code=status.HTTP_303_SEE_OTHER)
    return response


async def auth_index(request: Request, redirect_to: str, referer: str = Query(None), retry: int = Query(0)):
    """Core login form, used when no external Identity Provider is configured"""

    error_message = ""
    if retry == 1:
        error_message = "Invalid Credentials"

    if referer is None:
        referer = "/admin/"

    templates = get_jinja_templates()
    template_context = {
        "referer": referer,
        "error_message": error_message,
        "redirect_action": redirect_to
    }

    response = templates.TemplateResponse(
        request=request, name="auth/login.html", context=template_context
    )
    response.delete_cookie(key="ccat_user_token")
    return response


async def auth_token(request: Request, credentials: UserCredentials, agent_id: str):
    """Endpoint called from client to get a JWT from local identity provider.
    This endpoint receives username and password as form-data, validates credentials and issues a JWT.
    """

    # use username and password to authenticate user from local identity provider and get token
    access_token = await request.app.state.lizard.core_auth_handler.issue_jwt(
        credentials.username, credentials.password, key_id=agent_id
    )

    if access_token:
        return JWTResponse(access_token=access_token)

    # Invalid username or password
    # wait a little to avoid brute force attacks
    await asyncio.sleep(1)
    raise HTTPException(status_code=403, detail={"error": "Invalid Credentials"})
