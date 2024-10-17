from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict
from fastapi import Depends, APIRouter, HTTPException

from cat.auth.permissions import AuthPermission, AuthResource, get_base_permissions
from cat.auth.auth_utils import hash_password
from cat.auth.connection import HTTPAuth, ContextualCats
from cat.db.cruds import users as crud_users

router = APIRouter()


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


@router.post("/", response_model=UserResponse)
def create_user(
    new_user: UserCreate,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.USERS, AuthPermission.WRITE)),
):
    agent_id = cats.cheshire_cat.id
    created_user = crud_users.create_user(agent_id, new_user.model_dump())
    if not created_user:
        raise HTTPException(status_code=403, detail={"error": "Cannot duplicate user"})

    return created_user


@router.get("/", response_model=List[UserResponse])
def read_users(
    skip: int = 0,
    limit: int = 100,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.USERS, AuthPermission.LIST)),
):
    users_db = crud_users.get_users(cats.cheshire_cat.id)

    users = list(users_db.values())[skip: skip + limit]
    return users


@router.get("/{user_id}", response_model=UserResponse)
def read_user(
    user_id: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.USERS, AuthPermission.READ)),
):
    users_db = crud_users.get_users(cats.cheshire_cat.id)

    if user_id not in users_db:
        raise HTTPException(status_code=404, detail={"error": "User not found"})
    return users_db[user_id]


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    user: UserUpdate,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.USERS, AuthPermission.EDIT)),
):
    agent_id = cats.cheshire_cat.id
    stored_user = crud_users.get_user(agent_id, user_id)
    if not stored_user:
        raise HTTPException(status_code=404, detail={"error": "User not found"})
    
    if user.password:
        user.password = hash_password(user.password)
    updated_info = {**stored_user, **user.model_dump(exclude_unset=True)}

    crud_users.update_user(agent_id, user_id, updated_info)
    return updated_info


@router.delete("/{user_id}", response_model=UserResponse)
def delete_user(
    user_id: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.USERS, AuthPermission.DELETE)),
):
    agent_id = cats.cheshire_cat.id
    deleted_user = crud_users.delete_user(agent_id, user_id)
    if not deleted_user:
        raise HTTPException(status_code=404, detail={"error": "User not found"})

    return deleted_user
