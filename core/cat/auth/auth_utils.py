import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError
from fastapi.requests import HTTPConnection


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


def extract_chatbot_id_from_request(request: HTTPConnection) -> str:
    return request.headers.get(
        "chatbot_id",
        request.path_params.get(
            "chatbot_id",
            request.query_params.get(
                "chatbot_id",
                "chatbot"
            )
        )
    )


def extract_user_id_from_request(request: HTTPConnection) -> str:
    return request.headers.get(
        "user_id",
        request.path_params.get(
            "user_id",
            request.query_params.get(
                "user_id",
                "user"
            )
        )
    )