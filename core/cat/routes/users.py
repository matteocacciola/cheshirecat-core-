from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Dict
from fastapi import Depends, APIRouter

from cat.auth.permissions import AuthPermission, AuthResource, get_base_permissions
from cat.auth.auth_utils import hash_password
from cat.auth.connection import HTTPAuth, ContextualCats
from cat.db.cruds import users as crud_users
from cat.exceptions import CustomNotFoundException, CustomForbiddenException

router = APIRouter()


class UserBase(BaseModel):
    username: str = Field(min_length=2)
    permissions: Dict[str, List[str]] = get_base_permissions()

    @field_validator("permissions")
    def validate_permissions(cls, v):
        if not v:
            raise ValueError("Permissions cannot be empty")
        for k_, v_ in v.items():
            if not v_:
                raise ValueError(f"Permissions for {k_} cannot be empty")
            if k_ not in AuthResource:
                raise ValueError(f"Invalid resource: {k_}")
            if any([p not in AuthPermission for p in v_]):
                raise ValueError(f"Invalid permissions for {k_}")
        return v


class UserCreate(UserBase):
    id: str | None = None
    password: str = Field(min_length=5)
    # no additional fields allowed
    model_config = ConfigDict(extra="forbid")


class UserUpdate(UserBase):
    username: str = Field(default=None, min_length=2)
    password: str = Field(default=None, min_length=4)
    permissions: Dict[str, List[str]] = None
    model_config = ConfigDict(extra="forbid")

    @field_validator("permissions")
    def validate_permissions(cls, v):
        if v is None:
            return v
        return super().validate_permissions(v)


class UserResponse(UserBase):
    id: str


@router.post("/", response_model=UserResponse)
def create_user(
    new_user: UserCreate,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.USERS, AuthPermission.WRITE)),
) -> UserResponse:
    agent_id = cats.cheshire_cat.id
    created_user = crud_users.create_user(agent_id, new_user.model_dump())
    if not created_user:
        raise CustomForbiddenException("Cannot duplicate user")

    return UserResponse(**created_user)


@router.get("/", response_model=List[UserResponse])
def read_users(
    skip: int = 0,
    limit: int = 100,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.USERS, AuthPermission.LIST)),
) -> List[UserResponse]:
    users_db = crud_users.get_users(cats.cheshire_cat.id)

    users = list(users_db.values())[skip: skip + limit]
    return [UserResponse(**u) for u in users]


@router.get("/{user_id}", response_model=UserResponse)
def read_user(
    user_id: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.USERS, AuthPermission.READ)),
) -> UserResponse:
    users_db = crud_users.get_users(cats.cheshire_cat.id)

    if user_id not in users_db:
        raise CustomNotFoundException("User not found")
    return UserResponse(**users_db[user_id])


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    user: UserUpdate,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.USERS, AuthPermission.EDIT)),
) -> UserResponse:
    agent_id = cats.cheshire_cat.id
    stored_user = crud_users.get_user(agent_id, user_id)
    if not stored_user:
        raise CustomNotFoundException("User not found")
    
    if user.password:
        user.password = hash_password(user.password)
    updated_info = {**stored_user, **user.model_dump(exclude_unset=True)}

    crud_users.update_user(agent_id, user_id, updated_info)
    return UserResponse(**updated_info)


@router.delete("/{user_id}", response_model=UserResponse)
def delete_user(
    user_id: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.USERS, AuthPermission.DELETE)),
) -> UserResponse:
    agent_id = cats.cheshire_cat.id
    deleted_user = crud_users.delete_user(agent_id, user_id)
    if not deleted_user:
        raise CustomNotFoundException("User not found")

    return UserResponse(**deleted_user)
