from typing import List, Dict
from pydantic import BaseModel, Field, ConfigDict

from cat.auth.permissions import get_base_permissions


class UserBase(BaseModel):
    username: str = Field(min_length=2)
    permissions: Dict[str, List[str]] = get_base_permissions()


class UserCreate(UserBase):
    password: str = Field(min_length=5)
    # no additional fields allowed
    model_config = ConfigDict(extra="forbid")


class UserUpdate(UserBase):
    username: str = Field(default=None, min_length=2)
    password: str = Field(default=None, min_length=4)
    permissions: Dict[str, List[str]] = None
    model_config = ConfigDict(extra="forbid")


class UserResponse(UserBase):
    id: str
