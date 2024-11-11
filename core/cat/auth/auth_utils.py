import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError
from fastapi.requests import HTTPConnection
from pydantic import BaseModel

from cat.log import log
from cat.db.database import DEFAULT_AGENT_KEY, DEFAULT_SYSTEM_KEY

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_USER_USERNAME = "user"


class UserInfo(BaseModel):
    user_id: str
    username: str


def is_jwt(token: str) -> bool:
    """
    Returns whether a given string is a JWT.
    """
    try:
        # Decode the JWT without verification to check its structure
        jwt.decode(token, options={"verify_signature": False})
        return True
    except InvalidTokenError:
        return False

    
def hash_password(password: str) -> str:
    try:
        # Generate a salt
        salt = bcrypt.gensalt()
        # Hash the password
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")
    except Exception:
        # if you try something strange, you'll stay out
        return bcrypt.gensalt().decode("utf-8")


def check_password(password: str, hashed: str) -> bool:
    try:
        # Check if the password matches the hashed password
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def extract_user_id_from_request(request: HTTPConnection) -> str:
    return request.headers.get(
        "user_id",
        request.query_params.get("user_id")
    )


def extract_agent_id_from_request(request: HTTPConnection) -> str:
    return request.headers.get(
        "agent_id",
        request.path_params.get(
            "agent_id",
            request.query_params.get("agent_id", DEFAULT_AGENT_KEY)
        )
    )


def extract_user_info(agent_key: str, user_id: str | None = None) -> UserInfo | None:
    from cat.db.cruds import users as crud_users

    if user_id:
        user = crud_users.get_user(agent_key, user_id)
    else:
        # backward compatibility
        default = DEFAULT_ADMIN_USERNAME if agent_key == DEFAULT_SYSTEM_KEY else DEFAULT_USER_USERNAME
        user = crud_users.get_user_by_username(agent_key, default)

    if not user:
        return None

    return UserInfo(user_id=user["id"], username=user["username"])


def extract_token(request: HTTPConnection) -> str | None:
    # Proper Authorization header
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token:
        return token

    # Legacy header to pass CCAT_API_KEY
    token = request.headers.get("access_token", None)
    if token:
        log.warning(
            "Deprecation Warning: `access_token` header will not be supported in v2."
            "Pass your token/key using the `Authorization: Bearer <token>` format."
        )

    # some clients may send an empty string instead of just not setting the header
    return token