from typing import Dict
import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError
from fastapi import Request

from cat.db import crud


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
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    except Exception:
        # if you try something strange, you'll stay out
        return bcrypt.gensalt().decode("utf-8")


def check_password(password: str, hashed: str) -> bool:
    try:
        # Check if the password matches the hashed password
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False


def get_user_by_credentials(username: str, password: str, chatbot_id: str = "chatbot") -> Dict | None:
    """
    Get a user by their username and password. If the user is not found, return None.

    Args:
        username: the username of the user to look for
        password: the password of the user to look for
        chatbot_id: the chatbot ID to look for the user in (default: "chatbot")

    Returns:
        The user if found, None otherwise. The user has the format:
        {
            "id": <id_0>,
            "username": "<username_0>",
            "password": "<hashed_password_0>",
            "permissions": <dict_of_permissions_0>
        }
    """

    users = crud.get_users(chatbot_id=chatbot_id)
    for user in users.values():
        if user["username"] == username and user["password"] == hash_password(password):
            return user

    return None


def extract_chatbot_id_from_request(request: Request) -> str:
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
